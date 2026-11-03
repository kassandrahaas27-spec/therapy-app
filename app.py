import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json
from supabase import create_client, Client

st.set_page_config(page_title="Mon Therapy Suivi Global", page_icon="🤰", layout="centered")

# --- PARAMÈTRES DE CONNEXION SUPABASE SÉCURISÉS REELS ---
SUPABASE_URL = "https://fazxmveukiqpcefzghsr.supabase.co"
SUPABASE_KEY = "sb_publishable_VPYYOesD0T97zyl3V9b0Ng_VUXQ-lph"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

st.title("Mon suivi Therapy : Traitement, SOPK, Fertilité & Pré-Diabète")

def redemarrer():
    st.cache_data.clear()
    st.rerun()

# --- SYSTÈME DE CHARGEMENT SÉCURISÉ ---
@st.cache_data(ttl=60)
def load_db_from_supabase(table_name, columns):
    try:
        response = supabase.table(table_name).select("*").execute()
        if response.data:
            df = pd.DataFrame(response.data)
            if "Date" in df.columns: df["Date"] = df["Date"].astype(str)
            return df
        return pd.DataFrame(columns=columns)
    except:
        return pd.DataFrame(columns=columns)

def save_row_to_supabase(table_name, data_dict):
    try:
        supabase.table(table_name).insert(data_dict).execute()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde Cloud ({table_name}) : {e}")
        return False

# --- NOUVEAU : tableau modifiable (utilisé dans l'onglet Historique) ---
def editeur_table(df, table_name, key, choix=None):
    """Tableau modifiable : clique sur une case, change la valeur, puis enregistre."""
    if df.empty or "id" not in df.columns:
        st.dataframe(df, use_container_width=True)
        return
    df = df.reset_index(drop=True)
    non_editables = [c for c in ["id", "created_at"] if c in df.columns]
    config_cols = {c: st.column_config.SelectboxColumn(c, options=opts) for c, opts in (choix or {}).items() if c in df.columns}
    st.caption("✏️ Clique sur une case pour la modifier (dates au format AAAA-MM-JJ), puis enregistre.")
    edite = st.data_editor(df, key=key + "_" + str(len(df)), hide_index=True, disabled=non_editables, use_container_width=True, num_rows="fixed", column_config=config_cols)
    if st.button("💾 Enregistrer les modifications", key=key + "_btn"):
        nb = 0
        for i in range(len(df)):
            changements = {}
            for c in df.columns:
                if c in non_editables:
                    continue
                if str(df.at[i, c]) != str(edite.at[i, c]):
                    v = edite.at[i, c]
                    if pd.isna(v):
                        v = None
                    elif hasattr(v, "item"):
                        v = v.item()
                    changements[c] = v
            if changements:
                try:
                    supabase.table(table_name).update(changements).eq("id", int(df.at[i, "id"])).execute()
                    nb += 1
                except Exception as e:
                    st.error("Erreur de modification : " + str(e))
        if nb > 0:
            st.toast("🎉 " + str(nb) + " ligne(s) modifiée(s) !")
            redemarrer()
        else:
            st.info("Aucune modification détectée.")

# --- NOUVEAU : modifier le stock d'un médicament ---
def maj_stock(nom, config, nouveau_stock):
    config = dict(config)
    config["stock"] = max(0, int(nouveau_stock))
    try:
        supabase.table("medicaments").upsert({"name": nom, "config": config}).execute()
    except Exception as e:
        st.error("Erreur : " + str(e))
        return
    redemarrer()

# --- NOUVEAU : petits outils communs ---
MOMENTS_PRISE = [("Matin", "prend_matin", True), ("Midi", "prend_midi", False), ("Soir", "prend_soir", True), ("Coucher", "prend_coucher", False)]

def lundi_de(d_txt):
    try:
        d = datetime.strptime(str(d_txt), "%Y-%m-%d").date()
        return str(d - timedelta(days=d.weekday()))
    except Exception:
        return ""

def dose_actuelle_med(info):
    """Nombre de cachets par prise aujourd'hui (gère les paliers)."""
    dose = int(info.get("nb_cachet_par_repas", 1))
    if info.get("is_evolution", False) and "phases" in info:
        try:
            phases = info["phases"]
            if isinstance(phases, str):
                phases = json.loads(phases)
            p1 = phases[0]
            date_debut = datetime.strptime(info.get("start_date", str(date.today())), "%Y-%m-%d").date()
            duree = int(p1.get("duration", 7))
            if (date.today() - date_debut).days < duree:
                dose = int(p1.get("dose", 1))
            elif len(phases) > 1:
                dose = int(phases[1].get("dose", 2))
        except Exception:
            pass
    return dose

def charger_config(id_cfg):
    try:
        rep_c = supabase.table("config_grossesse").select("*").eq("id", id_cfg).execute()
        if rep_c.data:
            c = rep_c.data[0]["config"]
            return json.loads(c) if isinstance(c, str) else c
    except Exception:
        pass
    return {}

def sauver_config(id_cfg, cfg):
    try:
        supabase.table("config_grossesse").upsert({"id": id_cfg, "config": cfg}).execute()
        return True
    except Exception as e:
        st.error("Erreur d'enregistrement : " + str(e))
        return False

def bloc_suppression(df, table_name, key, colonnes_label):
    if df.empty or "id" not in df.columns:
        return
    opts = {}
    for _, r in df.iterrows():
        etiquette = " - ".join(str(r.get(c, "")) for c in colonnes_label) + " (n°" + str(r["id"]) + ")"
        opts[etiquette] = r["id"]
    choix_s = st.selectbox("Supprimer une ligne", list(opts.keys()), key=key + "_sel")
    if st.button("🚨 Supprimer", key=key + "_btn"):
        try:
            supabase.table(table_name).delete().eq("id", int(opts[choix_s])).execute()
        except Exception as e:
            st.error("Erreur de suppression : " + str(e))
            return
        redemarrer()

# --- NOUVEAU : tests d'ovulation (lecture de photo) ---
RESULTATS_TEST = [
    "Négatif (pas de ligne test ou ligne très faible)",
    "Ligne test visible mais plus claire que le contrôle",
    "Presque positif (presque aussi foncée que le contrôle)",
    "🥚 Pic LH (positif) : ligne test aussi foncée ou plus foncée que le contrôle",
]

def indice_depuis_ratio(r):
    if r < 0.15:
        return 0
    if r < 0.6:
        return 1
    if r < 1.0:
        return 2
    return 3

def miniature_base64(fichier):
    """Réduit la photo (600 px max) et la transforme en texte pour la stocker dans Supabase."""
    import base64, io
    from PIL import Image, ImageOps
    fichier.seek(0)
    img = ImageOps.exif_transpose(Image.open(fichier)).convert("RGB")
    img.thumbnail((600, 600))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()

def analyser_bandelette(fichier, position_controle):
    """Estime l'intensité de la ligne test par rapport à la ligne de contrôle.
    La photo doit être recadrée sur la fenêtre de lecture (les deux lignes visibles)."""
    import numpy as np
    from PIL import Image, ImageOps
    fichier.seek(0)
    img = ImageOps.exif_transpose(Image.open(fichier)).convert("RGB")
    angle = {"À droite": 0, "À gauche": 180, "En haut": -90, "En bas": 90}.get(position_controle, 0)
    if angle != 0:
        img = img.rotate(angle, expand=True)
    img.thumbnail((900, 900))
    vert = np.asarray(img).astype(float)[:, :, 1]
    h, w = vert.shape
    if w < 60 or h < 10:
        return {"ok": False, "message": "Photo trop petite ou mal cadrée.", "ratio": None, "profil": None}
    bande = vert[int(h * 0.3):int(h * 0.7), :]
    profil = pd.Series(bande.mean(axis=0))
    lisse = profil.rolling(5, center=True, min_periods=1).mean()
    fond = lisse.rolling(max(31, w // 5), center=True, min_periods=1).median()
    prof = (fond - lisse).clip(lower=0)
    marge = max(3, int(w * 0.04))
    prof.iloc[:marge] = 0
    prof.iloc[w - marge:] = 0
    seuil = max(4.0, 0.03 * float(fond.mean()))
    max_local = prof.rolling(15, center=True, min_periods=1).max()
    candidats = [i for i in range(w) if prof.iloc[i] >= seuil and prof.iloc[i] == max_local.iloc[i]]
    pics = []
    for i in candidats:
        if pics and i - pics[-1] < 15:
            if prof.iloc[i] > prof.iloc[pics[-1]]:
                pics[-1] = i
        else:
            pics.append(i)
    if len(pics) > 2:
        pics = sorted(sorted(pics, key=lambda k: prof.iloc[k], reverse=True)[:2])

    def aire(i):
        return float(prof.iloc[max(0, i - 8):i + 9].sum())

    if len(pics) == 0:
        return {"ok": False, "message": "Aucune ligne détectée : photo trop floue, trop sombre, mal cadrée, ou test invalide.", "ratio": None, "profil": prof}
    if len(pics) == 1:
        if pics[0] > w * 0.5:
            return {"ok": True, "message": "Une seule ligne détectée (côté contrôle) : pas de ligne test visible, donc test négatif.", "ratio": 0.0, "profil": prof}
        return {"ok": False, "message": "Une seule ligne détectée, côté test, sans ligne de contrôle : test invalide ou photo mal cadrée (vérifie le côté de la ligne de contrôle).", "ratio": None, "profil": prof}
    a_test, a_ctrl = aire(pics[0]), aire(pics[1])
    if a_ctrl <= 0:
        return {"ok": False, "message": "Ligne de contrôle illisible.", "ratio": None, "profil": prof}
    ratio = round(a_test / a_ctrl, 2)
    return {"ok": True, "message": "Ligne test = " + str(int(round(ratio * 100))) + " % de la ligne de contrôle.", "ratio": ratio, "profil": prof}

# Chargement sécurisé depuis Supabase
history_df = load_db_from_supabase("historique_prises", ["Date", "Médicament", "Prise", "Moment Repas", "Symptômes Traitement", "Symptômes SOPK/Pré-Diabète", "Note"])
cycle_df = load_db_from_supabase("cycle_temperature", ["Date", "Cycle Status", "Température", "Rapport Sexuel", "Note", "Mode Parcours"])
rdv_df = load_db_from_supabase("rdv_medicaux", ["Date", "Heure", "Médecin / Spécialité", "Lieu", "Notes"])
glyc_df_local = load_db_from_supabase("suivi_glycemie", ["Date", "Glycémie à jeun", "Glycémie Post-Prandiale"])
poids_df_local = load_db_from_supabase("suivi_poids", ["Date", "Poids (kg)", "Note", "Taille (cm)"])
tests_df = load_db_from_supabase("tests_ovulation", ["Date", "Heure", "Résultat", "Ratio", "Interprétation", "Photo", "Note"])
pma_df = load_db_from_supabase("suivi_pma", ["Date", "Étape Protocole", "Médicament / Injection", "Résultats Échographie", "Notes & Symptômes"])
examens_df = load_db_from_supabase("examens_pma", ["Date", "Examen", "Statut", "Résultat", "Note"])
questions_df = load_db_from_supabase("questions_medecin", ["Date", "Question", "Pour", "Posée", "Réponse"])
rdv_prendre_df = load_db_from_supabase("rdv_a_prendre", ["Spécialité", "Pour quoi", "Téléphone", "Statut", "Date appel", "Note"])
douleur_df = load_db_from_supabase("suivi_douleur_fatigue", ["Date", "Douleur (0-10)", "Fatigue (0-10)", "Sommeil (h)", "Qualité sommeil (0-10)", "Zones douloureuses", "Symptômes endométriose", "Note"])
bilans_df = load_db_from_supabase("resultats_bilans", ["Date", "Examen", "Valeur", "Unité", "Note"])

# Chargement sécurisé des médicaments
@st.cache_data(ttl=60)
def load_meds():
    resultat = {}
    try:
        rep = supabase.table("medicaments").select("*").execute()
        if rep.data:
            for row in rep.data:
                if isinstance(row, dict) and "name" in row and "config" in row:
                    c = row["config"]
                    resultat[row["name"]] = json.loads(c) if isinstance(c, str) else c
    except Exception:
        resultat = {}
    return resultat

@st.cache_data(ttl=60)
def load_config_grossesse():
    try:
        rep = supabase.table("config_grossesse").select("*").eq("id", 1).execute()
        if rep.data:
            c = rep.data[0]["config"]
            return json.loads(c) if isinstance(c, str) else c
    except Exception:
        pass
    return {}

meds = load_meds()
poids_config = load_config_grossesse()
    
# --- MENU DE GAUCHE ---
st.sidebar.header("⚙️ Configuration Globale")
parcours_mode = st.sidebar.selectbox("🌸 Ton parcours actuel :", ["Suivi de Cycle & Essai Bébé", "Suivi de Grossesse Évolutif", "Parcours PMA (Procréation Médicalement Assistée)"], key="side_parcours_mode")
jour_difficile = st.sidebar.checkbox("🌧️ Mode jour difficile (affichage simplifié)", key="side_jour_diff")
masquer_poids = st.sidebar.checkbox("🙈 Masquer le détail de mon poids", key="side_masquer_poids")

with st.sidebar.expander("✏️ Ajouter ou Modifier un Médicament", expanded=True):
    med_mode = st.sidebar.radio("Action", ["Nouveau médicament", "Modifier un existant"], key="side_med_mode")
    current_med_name = ""
    default_stock = 30
    default_timing = "Début de repas"
    default_m, default_mi, default_s, default_c = True, False, True, False
    default_is_evo = False
    default_nb_cachet = 1
    default_dur1 = 7
    default_d2 = 2
    
    if med_mode == "Modifier un existant" and meds:
        current_med_name = st.sidebar.selectbox("Choisir le médicament", list(meds.keys()), key="side_select_med")
        info_m = meds[current_med_name]
        default_stock = int(info_m.get("stock", 30))
        default_timing = info_m.get("timing", "Début de repas")
        default_m = info_m.get("prend_matin", True)
        default_mi = info_m.get("prend_midi", False)
        default_s = info_m.get("prend_soir", True)
        default_c = info_m.get("prend_coucher", False)
        default_is_evo = info_m.get("is_evolution", False)

    med_name = st.sidebar.text_input("Nom du médicament (ex: Metformine)", value=current_med_name if med_mode == "Modifier un existant" else "", key="side_med_name").strip()
    stock_actuel = st.sidebar.number_input("Stock de comprimés", min_value=0, value=default_stock, key="side_med_stock")
    timing = st.sidebar.selectbox("Moment lié au repas", ["Début de repas", "Milieu de repas", "Fin de repas"], index=0, key="side_med_timing")
    
    st.sidebar.markdown("**Moments de prise :**")
    p_matin = st.sidebar.checkbox("🌅 Matin", value=default_m, key="side_p_matin")
    p_midi = st.sidebar.checkbox("☀️ Midi", value=default_mi, key="side_p_midi")
    p_soir = st.sidebar.checkbox("🌙 Soir", value=default_s, key="side_p_soir")
    p_coucher = st.sidebar.checkbox("🛌 Coucher (ex : mélatonine)", value=default_c, key="side_p_coucher")
    
    date_debut_traitement = st.sidebar.date_input("📅 Date de début du traitement", value=date.today(), key="side_start_date")    

    is_evolution = st.sidebar.checkbox("🔄 Ce traitement est évolutif (Paliers)", value=default_is_evo, key="side_is_evo_cb")
    if is_evolution:
        d1 = st.sidebar.number_input("Dose Palier 1 (cachets/repas)", min_value=1, value=default_nb_cachet, key="side_d1_val")
        dur1 = st.sidebar.number_input("Durée Palier 1 (jours)", min_value=1, value=default_dur1, key="side_dur1_val")
        d2 = st.sidebar.number_input("Dose Palier 2 (cachets final)", min_value=1, value=default_d2, key="side_d2_val")
        phases_save = [{"dose": int(d1), "duration": int(dur1)}, {"dose": int(d2), "duration": 9999}]
        nb_cachets_repas = int(d1)
    else:
        nb_cachets_repas = st.sidebar.number_input("Nombre de cachet(s) par repas :", min_value=1, value=default_nb_cachet, key="side_nb_cachets_repas")
        phases_save = [{"dose": int(nb_cachets_repas), "duration": 9999}]

    if st.sidebar.button("💾 Enregistrer le médicament", key="side_save_med_btn"):
        if med_name:
            config_med = {
                "stock": int(stock_actuel), "timing": timing, "start_date": str(date_debut_traitement), "is_evolution": is_evolution, "phases": phases_save,                "prend_matin": p_matin, "prend_midi": p_midi, "prend_soir": p_soir, "prend_coucher": p_coucher, "nb_cachet_par_repas": int(nb_cachets_repas)
            }
            try:
                supabase.table("medicaments").upsert({"name": med_name, "config": config_med}).execute()
                st.sidebar.success("🎉 Médicament verrouillé sur le Cloud !")
                redemarrer()
            except Exception as e:
                st.sidebar.error(f"Erreur : {e}")

if meds:
    with st.sidebar.expander("🗑️ Supprimer un Médicament"):
        med_to_delete = st.sidebar.selectbox("Choisir à supprimer", list(meds.keys()), key="side_del_med_select")
        if st.sidebar.button("🚨 Confirmer la suppression"):
            supabase.table("medicaments").delete().eq("name", med_to_delete).execute()
            redemarrer()

# --- ONGLETS PRINCIPAUX ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📱 Tableau de Bord", "🌸 Mon Suivi Féminin", "📅 Rendez-vous Médicaux", "🥗 Suivi Glycémie & Nutrition", "📜 Historique & Corrections", "🧘 Douleur & Énergie", "📄 Fiche pour mes médecins"])

# --- TAB 1 : TABLEAU DE BORD ---
with tab1:
    st.subheader("📅 Prises du jour & Vos Symptômes")
    st.caption(f"Mode actif : **{parcours_mode}**")

    # NOUVEAU : choix du jour à enregistrer (en cas d'oubli)
    date_saisie = st.date_input("🗓️ Jour à enregistrer (tu peux revenir en arrière si tu as oublié)", value=date.today(), max_value=date.today(), key="t1_date_saisie")
    deja_saisi = []
    if not history_df.empty and "Date" in history_df.columns:
        deja_saisi = sorted(set(history_df[history_df["Date"] == str(date_saisie)]["Médicament"].tolist()))
    if deja_saisi:
        st.info("ℹ️ Il y a déjà des prises enregistrées le " + str(date_saisie) + " pour : " + ", ".join(deja_saisi) + ". Coche seulement ce qui n'est pas encore enregistré (ou corrige dans l'onglet Historique).")
    
    # --- NOUVEAU : À FAIRE POUR LA JOURNÉE ---
    st.write("### ✅ À faire pour le " + date_saisie.strftime("%d/%m/%Y"))
    manquants = {}
    for nom_m, info_m2 in meds.items():
        requis = [lib for lib, cle, defaut in MOMENTS_PRISE if info_m2.get(cle, defaut)]
        pris_txt = ""
        if not history_df.empty and all(c in history_df.columns for c in ["Date", "Médicament", "Prise"]):
            lignes_j = history_df[(history_df["Date"] == str(date_saisie)) & (history_df["Médicament"] == nom_m)]
            pris_txt = " ".join(lignes_j["Prise"].astype(str).tolist())
        manque = [lib for lib in requis if lib not in pris_txt]
        if manque:
            manquants[nom_m] = manque
    if not meds:
        st.caption("Ajoute un médicament dans le menu à gauche pour commencer.")
    elif manquants:
        for nom_m, manque in manquants.items():
            st.write("💊 **" + nom_m + "** : " + ", ".join(manque) + " à enregistrer")
    else:
        st.success("💊 Tous tes traitements sont enregistrés pour ce jour.")

    autres_taches = []
    if parcours_mode == "Suivi de Cycle & Essai Bébé":
        if cycle_df.empty or str(date_saisie) not in cycle_df["Date"].tolist():
            autres_taches.append("🌡️ Température basale pas encore notée (onglet Mon Suivi Féminin)")
    if glyc_df_local.empty or str(date_saisie) not in glyc_df_local["Date"].tolist():
        autres_taches.append("🩸 Pas de glycémie notée (seulement si ton médecin te l'a demandé)")
    if douleur_df.empty or str(date_saisie) not in douleur_df["Date"].tolist():
        autres_taches.append("🧘 Douleur, fatigue et sommeil pas encore notés (onglet Douleur & Énergie)")
    demain_txt = str(date.today() + timedelta(days=1))
    if not rdv_df.empty and "Date" in rdv_df.columns:
        for _, r_rdv in rdv_df.iterrows():
            if str(r_rdv.get("Statut", "")) == "✅ Effectué":
                continue
            if str(r_rdv["Date"]) in (str(date.today()), demain_txt):
                quand = "aujourd'hui" if str(r_rdv["Date"]) == str(date.today()) else "demain"
                h_rdv = r_rdv.get("Heure", "")
                h_rdv = "" if pd.isna(h_rdv) else str(h_rdv)
                autres_taches.append("📅 Rendez-vous " + quand + " : " + str(r_rdv.get("Médecin / Spécialité", "")) + " " + h_rdv)
    if not rdv_prendre_df.empty and "Statut" in rdv_prendre_df.columns:
        nb_appeler = int((rdv_prendre_df["Statut"] == "À appeler").sum())
        if nb_appeler > 0:
            autres_taches.append("📞 " + str(nb_appeler) + " rendez-vous à prendre (onglet Rendez-vous Médicaux)")
    for tache in autres_taches:
        st.write(tache)

    if manquants:
        if st.button("✅ J'ai tout pris comme d'habitude (enregistrer en un clic)", key="t1_tout_pris"):
            for nom_m, manque in manquants.items():
                total_clic = len(manque) * dose_actuelle_med(meds[nom_m])
                row_clic = {
                    "Date": str(date_saisie), "Médicament": nom_m, "Prise": ", ".join(manque) + f" ({total_clic} cachet(s))",
                    "Moment Repas": meds[nom_m].get("timing", ""), "Symptômes Traitement": "Aucun",
                    "Symptômes SOPK/Pré-Diabète": "Aucun", "Note": "Enregistré en un clic"
                }
                save_row_to_supabase("historique_prises", row_clic)
                info_clic = dict(meds[nom_m])
                info_clic["stock"] = max(0, int(info_clic.get("stock", 0)) - total_clic)
                supabase.table("medicaments").upsert({"name": nom_m, "config": info_clic}).execute()
            st.success("🎉 Enregistré !")
            redemarrer()
    st.write("---")

    if jour_difficile:
        st.info("🌧️ Mode jour difficile : seulement l'essentiel. Fais juste ce qui est listé ci-dessus. Tu pourras compléter le reste plus tard (tu peux revenir sur un jour passé avec le choix de date).")
    else:
        if not meds:
            st.info("Ajoute un médicament dans le menu à gauche pour commencer.")
        else:
            prises_details = {}
            for name, info in meds.items():
                st.write(f"#### 💊 {name}")

                dose_actuelle = int(info.get("nb_cachet_par_repas", 1))
                if info.get("is_evolution", False) and "phases" in info:
                    try:
                        phases = info["phases"]
                        if isinstance(phases, str):
                            phases = json.loads(phases)
                        p1 = phases[0]
                        date_debut = datetime.strptime(info.get("start_date", str(date.today())), "%Y-%m-%d").date()
                        duree = int(p1.get("duration", 7))
                        jours_ecoules = (date.today() - date_debut).days
                        if jours_ecoules < duree:
                            dose_actuelle = int(p1.get("dose", 1))
                            jours_restants = duree - jours_ecoules
                            date_changement = date_debut + timedelta(days=duree)
                            date_txt = date_changement.strftime("%d/%m/%Y")
                            dose_suivante = dose_actuelle
                            if len(phases) > 1:
                                dose_suivante = int(phases[1].get("dose", 2))
                            message = "⏳ Palier 1 en cours : prendre " + str(dose_actuelle) + " cachet(s) par repas. Passage à " + str(dose_suivante) + " cachet(s) le " + date_txt + " (dans " + str(jours_restants) + " jour(s))."
                            st.info(message)
                        else:
                            if len(phases) > 1:
                                dose_actuelle = int(phases[1].get("dose", 2))
                            st.success("🚀 Palier maximal atteint : dose stable de " + str(dose_actuelle) + " cachet(s).")
                    except Exception as e:
                        st.warning("Décompte indisponible : " + str(e))

                st.caption(f"Moments requis : {'🌅 Matin ' if info.get('prend_matin') else ''}{'☀️ Midi ' if info.get('prend_midi') else ''}{'🌙 Soir ' if info.get('prend_soir') else ''}{'🛌 Coucher' if info.get('prend_coucher') else ''} — Prendre **{dose_actuelle} cachet(s)** ({info.get('timing')})")
                # --- STOCK + ALERTE DE RACHAT ---
                stock_restant = int(info.get("stock", 0))
                nb_moments = sum([1 if info.get("prend_matin") else 0, 1 if info.get("prend_midi") else 0, 1 if info.get("prend_soir") else 0, 1 if info.get("prend_coucher") else 0])
                conso_jour = max(1, nb_moments * dose_actuelle)
                jours_stock = stock_restant // conso_jour
                date_fin_stock = date.today() + timedelta(days=jours_stock)

                if stock_restant == 0:
                    st.error("🚨 Stock épuisé ! Il faut racheter " + name + " tout de suite.")
                elif jours_stock <= 7:
                    st.warning("⚠️ Presque vide : il reste " + str(stock_restant) + " comprimé(s), soit environ " + str(jours_stock) + " jour(s) (jusqu'au " + date_fin_stock.strftime("%d/%m/%Y") + "). Pense à racheter " + name + " et à demander le renouvellement de l'ordonnance.")
                else:
                    st.caption("📦 Stock : " + str(stock_restant) + " comprimé(s), soit environ " + str(jours_stock) + " jour(s) (jusqu'au " + date_fin_stock.strftime("%d/%m/%Y") + ").")

                # NOUVEAU : modifier le stock facilement
                with st.expander("📦 Modifier le stock de " + name):
                    cs1, cs2 = st.columns(2)
                    with cs1:
                        stock_exact = st.number_input("Stock exact (comprimés)", min_value=0, value=stock_restant, step=1, key=f"stock_set_{name}_{stock_restant}")
                        if st.button("✏️ Corriger le stock", key=f"stock_set_btn_{name}"):
                            maj_stock(name, info, int(stock_exact))
                    with cs2:
                        stock_ajout = st.number_input("Ajouter (boîte rachetée)", min_value=0, value=0, step=1, key=f"stock_add_{name}_{stock_restant}")
                        if st.button("➕ Ajouter au stock", key=f"stock_add_btn_{name}"):
                            maj_stock(name, info, stock_restant + int(stock_ajout))

                col_m, col_mid, col_s, col_c = st.columns(4)
                matin_check, midi_check, soir_check, coucher_check = False, False, False, False
                with col_m:
                    if info.get("prend_matin", True): matin_check = st.checkbox("🌅 Pris le Matin", key=f"t1_{name}_matin_{date_saisie}")
                with col_mid:
                    if info.get("prend_midi", False): midi_check = st.checkbox("☀️ Pris le Midi", key=f"t1_{name}_midi_{date_saisie}")
                with col_s:
                    if info.get("prend_soir", True): soir_check = st.checkbox("🌙 Pris le Soir", key=f"t1_{name}_soir_{date_saisie}")
                with col_c:
                    if info.get("prend_coucher", False): coucher_check = st.checkbox("🛌 Pris au Coucher", key=f"t1_{name}_coucher_{date_saisie}")

                prises_details[name] = {"Matin": matin_check, "Midi": midi_check, "Soir": soir_check, "Coucher": coucher_check, "dose_unitaire": dose_actuelle}
                st.write("---")
            
            st.write("### 🧪 1. Effets Secondaires fréquents")
            symp_med_choisis = []
            liste_symp_med = ["Nausées / Vomissements", "Diarrhées", "Maux d'estomac / Brûlures", "Perte d'appétit", "Vertiges", "Bouffées de chaleur"]
            c_m1, c_m2 = st.columns(2)
            for idx, s in enumerate(liste_symp_med):
                with c_m1 if idx % 2 == 0 else c_m2:
                    if st.checkbox(s, key=f"t1_med_symptome_{s}_{date_saisie}"): symp_med_choisis.append(s)
                
            st.write("### 🌸 2. Symptômes liés au Cycle, SOPK & Glycémie")
            symp_cycle_choisis = []
            liste_symp_cycle = ["Coup de barre (Après repas)", "Envie de sucre subite", "Maux de tête / Migraine", "Crampes pelviennes / Ovaires", "Poussée d'acné", "Sauts d'humeur / Irritabilité", "Seins douloureux", "Rétention d'eau"]
            for idx, s in enumerate(liste_symp_cycle):
                if st.checkbox(s, key=f"t1_cycle_symptome_{s}_{date_saisie}"): symp_cycle_choisis.append(s)

            note_jour = st.text_input("Notes libres sur ta journée", placeholder="RAS", key=f"t1_note_libre_{date_saisie}")
        
            if st.button("✅ Enregistrer ma journée", key="t1_submit_bouton_validation_final_unique"):
                for name, moments in prises_details.items():
                    moments_cochés = [k for k, v in moments.items() if k in ["Matin", "Midi", "Soir", "Coucher"] and v]
                    if len(moments_cochés) > 0:
                        total_de_cachets_pris = len(moments_cochés) * moments["dose_unitaire"]
                        txt_prise = ", ".join(moments_cochés) + f" ({total_de_cachets_pris} cachet(s))"
                    else:
                        total_de_cachets_pris = 0
                        txt_prise = "Aucune"
                
                    row_data = {
                        "Date": str(date_saisie), "Médicament": name, "Prise": txt_prise, "Moment Repas": meds[name]["timing"], 
                        "Symptômes Traitement": ", ".join(symp_med_choisis) if symp_med_choisis else "Aucun",
                        "Symptômes SOPK/Pré-Diabète": ", ".join(symp_cycle_choisis) if symp_cycle_choisis else "Aucun", "Note": note_jour
                    }
                    save_row_to_supabase("historique_prises", row_data)
                
                    info_med = meds[name]
                    info_med["stock"] = max(0, int(info_med.get("stock", 30)) - total_de_cachets_pris)
                    supabase.table("medicaments").upsert({"name": name, "config": info_med}).execute()
                
                st.success("🎉 Enregistré dans ton cloud Supabase !")
                redemarrer()
def bloc_questions(prefix):
    st.write("#### ❓ Mes questions pour le médecin")
    q_txt = st.text_input("Une question à poser au prochain rendez-vous", key=prefix + "_q_txt")
    q_pour = st.selectbox("Pour qui ?", ["Équipe PMA / gynécologue", "Médecin traitant", "Endocrinologue / diabétologue", "Kiné", "Cardiologue", "Autre"], key=prefix + "_q_pour")
    if st.button("➕ Ajouter la question", key=prefix + "_q_add"):
        if q_txt.strip():
            if save_row_to_supabase("questions_medecin", {"Date": str(date.today()), "Question": q_txt.strip(), "Pour": q_pour, "Posée": "Non", "Réponse": ""}):
                redemarrer()
        else:
            st.warning("Écris d'abord ta question.")
    if not questions_df.empty:
        st.caption("Dans le tableau, mets « Posée » sur Oui une fois la question posée, et note la réponse.")
        editeur_table(questions_df, "questions_medecin", prefix + "_ed_questions", choix={"Posée": ["Non", "Oui"]})
        bloc_suppression(questions_df, "questions_medecin", prefix + "_q_del", ["Date", "Question"])

def carnet_pma():
    st.write("#### 🗂️ Mes examens PMA")
    st.caption("Cette liste est un exemple : suis seulement ce que ton médecin ou ton équipe PMA te prescrit.")
    e1, e2 = st.columns(2)
    with e1:
        ex_date = st.date_input("🗓️ Date (prévue ou réalisée)", value=date.today(), key="pma_ex_date")
    with e2:
        ex_nom = st.selectbox("Examen", ["Bilan hormonal (FSH, LH, œstradiol, AMH)", "Échographie pelvienne / comptage des follicules", "Hystérosalpingographie (trompes)", "Spermogramme (partenaire)", "Bilan thyroïdien (TSH)", "Bilan glycémique (HbA1c, glycémie à jeun)", "IRM pelvienne (endométriose)", "Autre"], key="pma_ex_nom")
    ex_autre = st.text_input("Nom de l'examen", key="pma_ex_autre") if ex_nom == "Autre" else ""
    ex_statut = st.selectbox("Où j'en suis", ["À prendre", "Rendez-vous pris", "Fait", "Résultat reçu"], key="pma_ex_statut")
    ex_res = st.text_input("Résultat / remarque", key="pma_ex_res")
    if st.button("💾 Enregistrer cet examen", key="pma_ex_save"):
        nom_ex = ex_autre.strip() if ex_nom == "Autre" and ex_autre.strip() else ex_nom
        if save_row_to_supabase("examens_pma", {"Date": str(ex_date), "Examen": nom_ex, "Statut": ex_statut, "Résultat": ex_res, "Note": ""}):
            redemarrer()
    if not examens_df.empty:
        editeur_table(examens_df, "examens_pma", "ed_examens", choix={"Statut": ["À prendre", "Rendez-vous pris", "Fait", "Résultat reçu"]})
        bloc_suppression(examens_df, "examens_pma", "pma_ex_del", ["Date", "Examen"])
    st.write("---")
    bloc_questions("pma")
    if not pma_df.empty:
        st.write("---")
        st.write("#### 💉 Mon protocole (historique)")
        editeur_table(pma_df, "suivi_pma", "ed_pma")
        bloc_suppression(pma_df, "suivi_pma", "pma_del", ["Date", "Étape Protocole"])

# --- TAB 2 : MON SUIVI FÉMININ ---
with tab2:
    if parcours_mode == "Suivi de Cycle & Essai Bébé":
        st.subheader("🌸 Suivi de Cycle, Courbe & Probabilité SOPK")
        
        cycle_date = st.date_input("🗓️ Date de l'événement", value=date.today(), key="t2_date_ess")
        col_c1, col_c2 = st.columns(2)
        with col_c1: cycle_status = st.selectbox("Statut du jour", ["Aucun Status", "🩸 Début des Règles", "❌ Fin des Règles", "💧 Spotting (Pertes)", "🥚 Test d'Ovulation Positif"], key="t2_status_ess")
        with col_c2: temperature = st.number_input("Température basale (°C)", min_value=35.0, max_value=41.0, value=36.5, step=0.05, key="t2_temp_ess")
        rapport_sexuel = st.checkbox("💞 Rapport sexuel ce jour-là", value=False, key="t2_rapport_ess")
        c_note = st.text_input("Notes particulières", key="t2_note_ess")
        
        if st.button("📊 Enregistrer cette journée", key="t2_submit_cycle_direct"):
            row_c = {"Date": str(cycle_date), "Cycle Status": cycle_status, "Température": temperature, "Rapport Sexuel": "Oui" if rapport_sexuel else "Non", "Note": c_note, "Mode Parcours": "Essai Bébé"}
            save_row_to_supabase("cycle_temperature", row_c)
            st.success("🎉 Sauvegardé sur le Cloud !")
            redemarrer()
                
        # ---------- TESTS D'OVULATION ----------
        st.write("---")
        st.write("### 🥚 Mes tests d'ovulation")

        regles_tests = []
        if not cycle_df.empty and "Cycle Status" in cycle_df.columns:
            regles_tests = sorted(set(cycle_df[cycle_df["Cycle Status"] == "🩸 Début des Règles"]["Date"].tolist()))
        if regles_tests:
            dernieres_r = datetime.strptime(regles_tests[-1], "%Y-%m-%d").date()
            longueurs = []
            for a_r, b_r in zip(regles_tests[:-1], regles_tests[1:]):
                dif = (datetime.strptime(b_r, "%Y-%m-%d").date() - datetime.strptime(a_r, "%Y-%m-%d").date()).days
                if 15 <= dif <= 90:
                    longueurs.append(dif)
            long_cycle = int(round(sum(longueurs) / len(longueurs))) if longueurs else 35
            debut_tests = dernieres_r + timedelta(days=9)
            fin_tests = dernieres_r + timedelta(days=max(long_cycle - 10, 14))
            jour_cycle = (date.today() - dernieres_r).days + 1
            st.write("**📅 Quand faire les tests ?**")
            st.markdown(
                "* Tu es au **jour " + str(jour_cycle) + "** de ton cycle (cycle moyen estimé : **" + str(long_cycle) + " jours**" + ("" if longueurs else ", valeur par défaut faute d'historique") + ").\n"
                "* **Période conseillée :** du **" + debut_tests.strftime("%d/%m/%Y") + "** (jour 10) au **" + fin_tests.strftime("%d/%m/%Y") + "**, ou jusqu'au premier pic."
            )
            if date.today() < debut_tests:
                st.info("⏳ Pas encore : commence dans " + str((debut_tests - date.today()).days) + " jour(s).")
            elif date.today() <= fin_tests:
                st.success("✅ C'est la période des tests : fais-en un aujourd'hui (une fois par jour, toujours à la même heure).")
            else:
                st.info("La période conseillée est passée. Si tu n'as pas eu de pic, continue ta courbe de température et parles-en à ton médecin si tes cycles sont très longs.")
        else:
            st.info("💡 Enregistre un jour avec le statut « 🩸 Début des Règles » pour que l'appli calcule tes dates de tests. En attendant : commence vers le jour 10 de ton cycle.")

        with st.expander("ℹ️ Comment bien faire le test et reconnaître un pic"):
            st.markdown("""
* **Une fois par jour**, toujours à la même heure, plutôt **entre 10 h et 20 h** (début d'après-midi idéal). Évite la première urine du matin.
* **Bois peu pendant les 2 heures avant** le test, sinon l'urine est trop diluée et la ligne peut sembler plus claire.
* Lis le résultat **dans le délai du mode d'emploi** (souvent 5 minutes). Une lecture trop tardive peut tromper.
* Quand la ligne test se **rapproche** de la ligne de contrôle, fais **2 tests par jour** (par exemple 10 h et 18 h) pour ne pas rater le pic.
* **Pic (positif)** : la ligne test est **aussi foncée ou plus foncée** que la ligne de contrôle. L'ovulation arrive en général **12 à 36 heures environ** après. Rapports le jour du pic et le lendemain.
* **Ligne test plus claire que le contrôle** : ce n'est pas encore un pic. Continue.
* **Avec un SOPK**, l'hormone LH est souvent élevée en permanence : le test peut donner des **lignes foncées sans ovulation** (faux positifs). Ne te fie pas qu'au test : ta **courbe de température** confirme l'ovulation après coup (hausse durable). Parles-en à ton médecin si tu as plusieurs pics sans hausse de température.
            """)

        t_col1, t_col2 = st.columns(2)
        with t_col1:
            test_date = st.date_input("🗓️ Date du test", value=date.today(), max_value=date.today(), key="t2_test_date")
        with t_col2:
            test_heure = st.text_input("Heure du test", placeholder="15:00", key="t2_test_heure")

        if "photo_test_n" not in st.session_state:
            st.session_state["photo_test_n"] = 0
        st.write("**📸 Photo du test (facultatif) : l'appli estime si c'est un pic**")
        st.caption("Recadre la photo sur la fenêtre de lecture, avec les deux lignes bien visibles, en pleine lumière, sans reflet ni ombre. Le résultat est une estimation : vérifie toujours à l'œil.")
        pos_controle = st.selectbox("Sur ta photo, où est la ligne de contrôle (C) ?", ["En haut", "En bas", "À droite", "À gauche"], key="t2_test_pos")
        fichier_up = st.file_uploader("Importer une photo", type=["jpg", "jpeg", "png"], key="t2_test_photo_" + str(st.session_state["photo_test_n"]))
        photo_cam = None
        if st.checkbox("📷 Prendre la photo avec l'appareil", key="t2_test_cam_cb"):
            photo_cam = st.camera_input("Photo du test", key="t2_test_cam_" + str(st.session_state["photo_test_n"]))
        fichier_photo = photo_cam if photo_cam is not None else fichier_up

        analyse_test = None
        idx_suggere = 0
        if fichier_photo is not None:
            st.image(fichier_photo, width=300)
            try:
                analyse_test = analyser_bandelette(fichier_photo, pos_controle)
            except Exception as e:
                st.warning("Analyse impossible : " + str(e))
            if analyse_test:
                if analyse_test["ok"]:
                    idx_suggere = indice_depuis_ratio(analyse_test["ratio"])
                    st.info("🔎 Estimation de l'appli : " + analyse_test["message"] + " → **" + RESULTATS_TEST[idx_suggere] + "**")
                else:
                    st.warning("🔎 " + analyse_test["message"])
                if analyse_test.get("profil") is not None:
                    with st.expander("📈 Voir comment la photo a été lue"):
                        st.caption("Les deux creux = les deux lignes. Plus le creux est profond, plus la ligne est foncée.")
                        st.line_chart(analyse_test["profil"].reset_index(drop=True))

        resultat_test = st.selectbox("Résultat du test (tu peux corriger l'estimation)", RESULTATS_TEST, index=idx_suggere, key="t2_test_res_" + str(idx_suggere) + "_" + str(st.session_state["photo_test_n"]))
        if resultat_test.startswith("🥚 Pic"):
            st.success("🎉 Pic détecté ! L'ovulation est attendue dans les 12 à 36 heures environ : rapports aujourd'hui et demain. Note aussi ta température chaque matin pour confirmer.")
        elif resultat_test.startswith("Presque"):
            st.warning("⏳ Presque : refais un test dans 4 à 6 heures (ou ce soir) pour ne pas rater le pic.")
        elif resultat_test.startswith("Ligne test visible"):
            st.info("📈 L'hormone LH monte. Continue les tests, 2 fois par jour maintenant.")
        else:
            st.caption("Pas de pic pour le moment. Continue les tests à la même heure chaque jour.")
        test_note = st.text_input("Note (facultatif)", key="t2_test_note")

        if st.button("🥚 Enregistrer ce test", key="t2_test_save"):
            try:
                photo_b64 = miniature_base64(fichier_photo) if fichier_photo is not None else ""
            except Exception:
                photo_b64 = ""
            ratio_txt = ""
            interp_txt = ""
            if analyse_test:
                interp_txt = analyse_test["message"]
                if analyse_test["ratio"] is not None:
                    ratio_txt = str(analyse_test["ratio"])
            row_test = {"Date": str(test_date), "Heure": test_heure, "Résultat": resultat_test, "Ratio": ratio_txt, "Interprétation": interp_txt, "Photo": photo_b64, "Note": test_note}
            if save_row_to_supabase("tests_ovulation", row_test):
                st.session_state["photo_test_n"] += 1
                st.success("🎉 Test enregistré !")
                redemarrer()

        if not tests_df.empty:
            st.write("**📋 Mes tests**")
            tests_aff = tests_df.drop(columns=[c for c in ["Photo", "created_at"] if c in tests_df.columns]).sort_values(by="Date", ascending=False).reset_index(drop=True)
            st.dataframe(tests_aff, use_container_width=True)

            if "Ratio" in tests_df.columns:
                tn = tests_df.copy()
                tn["Ratio_num"] = pd.to_numeric(tn["Ratio"], errors="coerce")
                tn = tn.dropna(subset=["Ratio_num"]).sort_values(by=["Date", "Heure"]).reset_index(drop=True)
                if len(tn) >= 2:
                    import altair as alt
                    tn["Date_dt"] = pd.to_datetime(tn["Date"])
                    courbe_tests = alt.Chart(tn).mark_line(point=True, color="#9467bd").encode(
                        x=alt.X("Date_dt:T", title="Date"), y=alt.Y("Ratio_num:Q", title="Ligne test / contrôle"), tooltip=["Date", "Heure", "Ratio_num"]
                    )
                    trait_pic = alt.Chart(pd.DataFrame({"y": [1.0]})).mark_rule(color="red", strokeDash=[4, 4]).encode(y="y:Q")
                    st.altair_chart((courbe_tests + trait_pic).properties(width=450, height=200), use_container_width=False)
                    st.caption("Le trait rouge = ligne test aussi foncée que le contrôle (pic). Au-dessus ou sur le trait = pic.")

            if "Photo" in tests_df.columns and "id" in tests_df.columns:
                avec_photo = tests_df[tests_df["Photo"].fillna("").astype(str).str.len() > 10]
                if not avec_photo.empty:
                    import base64
                    opts_ph = {str(r["Date"]) + " " + str(r.get("Heure", "")) + " (n°" + str(r["id"]) + ")": r["Photo"] for _, r in avec_photo.iterrows()}
                    ph_choisie = st.selectbox("📸 Revoir une photo", list(opts_ph.keys()), key="t2_test_ph_sel")
                    st.image(base64.b64decode(opts_ph[ph_choisie]), width=300)

            if "id" in tests_df.columns:
                opts_tdel = {str(r["Date"]) + " " + str(r.get("Heure", "")) + " (n°" + str(r["id"]) + ")": r["id"] for _, r in tests_df.iterrows()}
                tdel_choisi = st.selectbox("Supprimer un test", list(opts_tdel.keys()), key="t2_test_del_sel")
                if st.button("🚨 Supprimer ce test", key="t2_test_del_btn"):
                    try:
                        supabase.table("tests_ovulation").delete().eq("id", int(opts_tdel[tdel_choisi])).execute()
                        redemarrer()
                    except Exception as e:
                        st.error("Erreur de suppression : " + str(e))
        with st.expander("🧬 Mon carnet PMA (examens, questions, protocole)"):
            carnet_pma()
        st.write("---")

        if not cycle_df.empty:
            import altair as alt

            # --- Courbe avec un trait rouge et une couleur par cycle ---
            cg = cycle_df.copy()
            cg["Température"] = pd.to_numeric(cg["Température"], errors="coerce")
            debuts_regles = sorted(set(cg[cg["Cycle Status"] == "🩸 Début des Règles"]["Date"].tolist()))
            cg = cg.dropna(subset=["Température"]).sort_values(by="Date").reset_index(drop=True)

            def _num_cycle(d):
                return sum(1 for x in debuts_regles if x <= d)

            def _label_cycle(n):
                if n == 0:
                    return "Avant le 1er cycle noté"
                dd = datetime.strptime(debuts_regles[n - 1], "%Y-%m-%d").strftime("%d/%m")
                return "Cycle " + str(n) + " (début " + dd + ")"

            def _jour_cycle(row):
                if row["N"] == 0:
                    return None
                debut = datetime.strptime(debuts_regles[row["N"] - 1], "%Y-%m-%d")
                return (datetime.strptime(row["Date"], "%Y-%m-%d") - debut).days + 1

            cg["N"] = cg["Date"].apply(_num_cycle)
            cg["Cycle"] = cg["N"].apply(_label_cycle)
            cg["Jour du cycle"] = cg.apply(_jour_cycle, axis=1)
            cg["Date_dt"] = pd.to_datetime(cg["Date"])

            ligne = alt.Chart(cg).mark_line(point=True).encode(
                x=alt.X("Date_dt:T", title="Date"),
                y=alt.Y("Température:Q", title="°C Basale", scale=alt.Scale(domain=[35.0, 37.5])),
                color=alt.Color("Cycle:N", title="Cycle", legend=alt.Legend(orient="bottom")),
                tooltip=["Date", "Température", "Cycle", "Jour du cycle"]
            )
            if debuts_regles:
                regles_marq = pd.DataFrame({"Date_dt": pd.to_datetime(debuts_regles), "Label": ["🩸 Règles"] * len(debuts_regles)})
                traits = alt.Chart(regles_marq).mark_rule(color="red", strokeDash=[4, 4]).encode(x="Date_dt:T")
                textes = alt.Chart(regles_marq).mark_text(align="left", dx=4, color="red").encode(x="Date_dt:T", y=alt.value(10), text="Label:N")
                graphique_zoome = (ligne + traits + textes).properties(width=450, height=280)
            else:
                graphique_zoome = ligne.properties(width=450, height=280)
            st.altair_chart(graphique_zoome, use_container_width=False)
            if not debuts_regles:
                st.caption("💡 Enregistre un jour avec le statut « 🩸 Début des Règles » pour voir apparaître chaque nouveau cycle sur la courbe.")

            # --- Comparaison des cycles superposés ---
            cg_cmp = cg[cg["N"] >= 1]
            if cg_cmp["N"].nunique() >= 2:
                with st.expander("🔍 Comparer mes cycles (superposés : jour 1 = début des règles)"):
                    comparaison = alt.Chart(cg_cmp).mark_line(point=True).encode(
                        x=alt.X("Jour du cycle:Q", title="Jour du cycle"),
                        y=alt.Y("Température:Q", title="°C Basale", scale=alt.Scale(domain=[35.0, 37.5])),
                        color=alt.Color("Cycle:N", title="Cycle", legend=alt.Legend(orient="bottom")),
                        tooltip=["Date", "Température", "Cycle", "Jour du cycle"]
                    ).properties(width=450, height=280)
                    st.altair_chart(comparaison, use_container_width=False)

            st.write("### 🔮 Analyse de ton Cycle & Fertilité SOPK")
            cycle_tri = cycle_df.copy()
            cycle_tri["Température"] = pd.to_numeric(cycle_tri["Température"], errors="coerce")
            cycle_tri = cycle_tri.dropna(subset=["Température"]).sort_values(by="Date").reset_index(drop=True)
            temps_list = cycle_tri["Température"].tolist()
            status_list = cycle_tri["Cycle Status"].tolist()
            rapports_list = cycle_tri["Rapport Sexuel"].tolist()
            dates_list = cycle_tri["Date"].tolist()

            date_ovulation_reelle = None
            date_hausse = None
            if len(temps_list) >= 9:
                for i in range(6, len(temps_list) - 2):
                    base = max(temps_list[i-6:i])
                    if temps_list[i] > base and temps_list[i+1] > base and temps_list[i+2] >= base + 0.2:
                        date_hausse = datetime.strptime(dates_list[i], "%Y-%m-%d").date()
                        date_ovulation_reelle = date_hausse - timedelta(days=1)

            st.write("#### 🌡️ Ovulation estimée selon ta courbe")
            if date_ovulation_reelle:
                st.success("🥚 Hausse de température détectée à partir du " + date_hausse.strftime("%d/%m/%Y") + ". Ovulation probable vers le **" + date_ovulation_reelle.strftime("%d/%m/%Y") + "** (à 1 jour près).")
            elif len(temps_list) < 9:
                st.info("Il faut au moins 9 températures enregistrées pour détecter une hausse. Tu en as " + str(len(temps_list)) + ".")
            else:
                st.info("Pas de hausse nette détectée pour le moment. Continue à prendre ta température chaque matin.")

            test_positif_recent = False
            if not tests_df.empty and "Résultat" in tests_df.columns:
                limite_tests = str(date.today() - timedelta(days=5))
                test_positif_recent = not tests_df[(tests_df["Date"] >= limite_tests) & (tests_df["Résultat"].astype(str).str.startswith("🥚 Pic"))].empty
            test_ovulation_recent = ("🥚 Test d'Ovulation Positif" in status_list[-5:]) or test_positif_recent
            rapport_recent = "Oui" in rapports_list[-3:]

            if test_ovulation_recent and rapport_recent:
                st.metric(label="Chances de conception estimées", value="85% - 95%", delta="Optimale (Rapport + Test OK)", delta_color="inverse")
            elif date_ovulation_reelle and "Oui" in rapports_list[-5:]:
                st.metric(label="Chances de conception estimées", value="60% - 75%", delta="Très bonne (Hausse thermique validée)")
            else:
                st.metric(label="Chances de conception estimées", value="10% - 15%", delta="Phase standard / d'attente")

            st.write("#### 📅 Mon Calendrier Prédictif du Cycle")
            regles_dates = cycle_df[cycle_df["Cycle Status"] == "🩸 Début des Règles"]["Date"].tolist()

            if regles_dates:
                dernieres_regles = datetime.strptime(sorted(regles_dates)[-1], "%Y-%m-%d").date()
                if date_ovulation_reelle:
                    prochaines_regles = date_ovulation_reelle + timedelta(days=14)
                    debut_fertilite = date_ovulation_reelle - timedelta(days=4)
                    fin_fertilite = date_ovulation_reelle + timedelta(days=1)
                    jour_test_grossesse = date_ovulation_reelle + timedelta(days=14)
                else:
                    prochaines_regles = dernieres_regles + timedelta(days=35)
                    debut_fertilite = prochaines_regles - timedelta(days=18)
                    fin_fertilite = prochaines_regles - timedelta(days=14)
                    jour_test_grossesse = prochaines_regles

                st.markdown(f"""
                * **🩸 Prochaines règles estimées :** autour du **{prochaines_regles.strftime('%d/%m/%Y')}**.
                * **🥚 Prochaine fenêtre de fertilité :** du **{debut_fertilite.strftime('%d/%m/%Y')}** au **{fin_fertilite.strftime('%d/%m/%Y')}**.
                * **🧪 Date idéale Test de Grossesse :** à partir du **{jour_test_grossesse.strftime('%d/%m/%Y')}**.
                """)
            else:
                st.caption("💡 Ajoute un événement '🩸 Début des Règles' pour activer les prédictions.")

    elif parcours_mode == "Suivi de Grossesse Évolutif":
        st.subheader("Mon Suivi de Grossesse")
        
        # CONFIGURATION DPA / OVULATION
        methode_calcul = st.radio("Méthode :", ["Entrer ma date d'ovulation / conception", "Entrer ma date de terme officielle (DPA)"], key="t2_methode_calcul")
        if methode_calcul == "Entrer ma date d'ovulation / conception":
            ovul_defaut_in = poids_config.get("date_ovulation", str(date.today() - timedelta(days=35)))
            date_ovul = st.date_input("🗓️ Date exacte de ton ovulation :", value=datetime.strptime(ovul_defaut_in, "%Y-%m-%d").date(), key="t2_grossesse_ovul")
            date_terme = date_ovul + timedelta(days=273)
        else:
            dpa_defaut = poids_config.get("dpa", str(date.today() + timedelta(days=240)))
            date_terme = st.date_input("🗓️ Date Prévue d'Accouchement (Terme) :", value=datetime.strptime(dpa_defaut, "%Y-%m-%d").date(), key="t2_grossesse_dpa")
            date_ovul = date_terme - timedelta(days=273)

        if st.button("💾 Sauvegarder mon calendrier", key="btn_save_dpa_sopk"):
            poids_config["dpa"] = str(date_terme)
            poids_config["date_ovulation"] = str(date_ovul)
            supabase.table("config_grossesse").upsert({"id": 1, "config": json.dumps(poids_config)}).execute()
            st.success("🎉 Calendrier mis à jour !")
            redemarrer()
            
        date_debut_sa = date_ovul - timedelta(days=14)
        jours_totaux_sa = (date.today() - date_debut_sa).days
        sa_semaines = max(0, jours_totaux_sa // 7)
        sa_jours = max(0, jours_totaux_sa % 7)

        st.metric(label="🤰 Où j'en suis", value=str(sa_semaines) + " SA + " + str(sa_jours) + " J")
        st.caption("Date prévue d'accouchement : " + date_terme.strftime("%d/%m/%Y"))

        st.write("### 📢 L'évolution de bébé cette semaine")
        if sa_semaines <= 6:
            st.success("🌱 **Phase embryonnaire précoce :** L'embryon se structure. Prends ton acide folique.")
        elif 7 <= sa_semaines <= 10:
            st.success("🍋 **Évolution Morphologique :** Bébé fait la taille d'une framboise. Fractionne tes assiettes contre les nausées.")
        elif 11 <= sa_semaines <= 14:
            st.success("🍓 **Fin du 1er trimestre :** Les traits se précisent, l'échographie T1 approche.")
        elif 15 <= sa_semaines <= 19:
            st.success("🍏 **Deuxième trimestre confortable :** Bébé grandit, poursuis ta marche active pour l'insuline.")
        elif 20 <= sa_semaines <= 24:
            st.success("🍌 **Échographie Morphologique (T2) :** Bébé bouge beaucoup et commence à entendre tes sons.")
        elif 25 <= sa_semaines <= 28:
            st.success("🥕 **Vigilance métabolique :** C'est la période du test HGPO. Reste rigoureuse sur l'eau pure.")
        elif 29 <= sa_semaines <= 32:
            st.success("🥥 **Échographie T3 en approche :** Bébé s'arrondit. Mange en plus petites quantités pour éviter les reflux.")
        elif 33 <= sa_semaines <= 36:
            st.success("🍍 **Préparation :** Bébé commence à se retourner tête en bas. Prépare ta valise de maternité.")
        else:
            st.success("🍉 **Mois du terme :** Bébé est prêt à naître à tout moment. Repose-toi au maximum.")

        # --- BLOC BEBE SECRET ---
        st.write("### 👶 Informations Secrètes sur Bébé(s)")
        genre_bebe_choix = ["Non renseigné / Winter Surprise 🤫", "Fille 🌸", "Garçon 💎", "Jumeaux / Grossesse Multiple 🤰🤰"]
        poids_config["genre_bebe"] = st.selectbox("👶 Genre du bébé :", genre_bebe_choix, index=genre_bebe_choix.index(poids_config.get("genre_bebe", "Non renseigné / Winter Surprise 🤫")), key="t2_genre_bebe_sel")
        poids_config["notes_bebe"] = st.text_input("📝 Notes sur les Échographies", value=poids_config.get("notes_bebe", ""), key="t2_notes_bebe_txt")

        # --- CARNET DE BORD CLINIQUE ET RANGE-DOCUMENTS ULTRA COMPLET ---
        with st.expander("📁 Range-Documents : Mesures Échographies, Suivi Sage-Femme & Monitorings"):
            st.caption("💡 Centralise ici tes résultats médicaux officiels pour les avoir sous les yeux face aux spécialistes :")
            
            st.markdown("**🖼️ ÉCHOGRAPHIES OBSTÉTRICALES :**")
            poids_config["doc_lcc"] = st.text_input("Écho T1 - Longueur Cranio-Caudale (LCC en mm) :", value=poids_config.get("doc_lcc", ""), key="t2_lcc")
            poids_config["doc_cn"] = st.text_input("Écho T1 - Clarté Nucale (CN en mm) :", value=poids_config.get("doc_cn", ""), key="t2_cn")
            poids_config["doc_bip"] = st.text_input("Écho T2 - Diamètre Bi-Pariétal de la tête (BIP en mm) :", value=poids_config.get("doc_bip", ""), key="t2_bip")
            poids_config["doc_poids_est"] = st.text_input("Écho T3 - Estimation du poids fœtal actuel (en grammes) :", value=poids_config.get("doc_poids_est", ""), key="t2_poids_est")
            
            st.markdown("---")
            st.markdown("**🩺 CONSULTATIONS SAGE-FEMME / GYNECO :**")
            poids_config["doc_col"] = st.text_input("Mesure ou état du Col Utérin (ex: Long, Tonique, Fermé) :", value=poids_config.get("doc_col", ""), key="t2_col")
            poids_config["doc_hu"] = st.text_input("Hauteur Utérine (HU en cm) :", value=poids_config.get("doc_hu", ""), key="t2_hu")
            poids_config["doc_tension"] = st.text_input("Tension artérielle maximale lue en cabinet (ex: 12/7) :", value=poids_config.get("doc_tension", ""), key="t2_tension")
            
            st.markdown("---")
            st.markdown("**💓 MONITORINGS DU 3ÈME TRIMESTRE (RCF) :**")
            poids_config["doc_monitoring"] = st.text_input("Rythme Cardiaque Fœtal & Contractions (ex: Réactif, RAS) :", value=poids_config.get("doc_monitoring", ""), key="t2_monit")
            
            st.markdown("---")
            st.markdown("**🩸 BILANS BIOLOGIQUES (LABORATOIRE) :**")
            poids_config["doc_toxo"] = st.selectbox("Statut Sérologie Toxoplasmose :", ["Non immunisée (Prise de sang mensuelle obligatoire) 🩸", "Immunisée ✅"], index=0 if poids_config.get("doc_toxo", "") == "" or "Non" in poids_config.get("doc_toxo", "") else 1, key="t2_toxo_stat")
            poids_config["doc_glycosurie"] = st.text_input("Analyse d'urine mensuelle - Glycosurie (g/L) :", value=poids_config.get("doc_glycosurie", ""), key="t2_glycurie")
            poids_config["doc_albuminurie"] = st.text_input("Analyse d'urine mensuelle - Albuminurie / Protéinurie (g/L) :", value=poids_config.get("doc_albuminurie", ""), key="t2_alburie")
        
        # --- CHECKLIST COMPLETISSIME VALISE MATERNITÉ ---
        with st.expander("🍼 Checklist : La Valise de Maternité Complète (Maman, Bébé & Papa)"):
            st.write("**👶 POUR BÉBÉ :**")
            poids_config["v_body"] = st.checkbox("6 bodys en coton (ouverture croisée sur le devant)", value=poids_config.get("v_body", False), key="v1")
            poids_config["v_pyj"] = st.checkbox("6 pyjamas en velours chauds (dors-bien)", value=poids_config.get("v_pyj", False), key="v2")
            poids_config["v_brass"] = st.checkbox("3 brassières ou gilets en laine", value=poids_config.get("v_brass", False), key="v_b1")
            poids_config["v_chauss"] = st.checkbox("4 paires de chaussettes + 1 paire de chaussons", value=poids_config.get("v_chauss", False), key="v_c1")
            poids_config["v_bonnet"] = st.checkbox("2 bonnets de naissance en coton / laine", value=poids_config.get("v_bonnet", False), key="v5")
            poids_config["v_turb"] = st.checkbox("2 gigoteuses / turbulettes (taille 0-6 mois)", value=poids_config.get("v_turb", False), key="v4")
            poids_config["v_lange"] = st.checkbox("5 langes en tissu (indispensables pour les rejets)", value=poids_config.get("v_lange", False), key="v_l1")
            poids_config["v_sortie"] = st.checkbox("1 nid d'ange ou couverture chaude pour la sortie", value=poids_config.get("v_sortie", False), key="v_s1")
            
            st.write("---")
            st.write("**🤰 POUR MAMAN :**")
            poids_config["v_adm"] = st.checkbox("Dossier médical complet (Carte vitale, carte groupe sanguin, échos, bilans)", value=poids_config.get("v_adm", False), key="v6")
            poids_config["v_confort"] = st.checkbox("3 ou 4 tenues très amples, pyjamas confortables et vêtements de nuit", value=poids_config.get("v_confort", False), key="v7")
            poids_config["v_chaussons"] = st.checkbox("1 paire de claquettes ou chaussons faciles à enfiler", value=poids_config.get("v_chaussons", False), key="v_ch2")
            poids_config["v_hyg"] = st.checkbox("Trousse de toilette complète + serviettes hygiéniques de maternité (nuit/maxi)", value=poids_config.get("v_hyg", False), key="v8")
            poids_config["v_slip"] = st.checkbox("5 slips jetables en filet ou culottes en coton jetables", value=poids_config.get("v_slip", False), key="v_sl2")
            poids_config["v_allait"] = st.checkbox("Si allaitement : 2 soutiens-gorge d'allaitement + coussinets + crème lanoline", value=poids_config.get("v_allait", False), key="v_al2")
            poids_config["v_brume"] = st.checkbox("1 brumisateur d'eau thermale (magique pour la salle de naissance)", value=poids_config.get("v_brume", False), key="v_br2")
            
            st.write("---")
            st.write("**🧔 POUR LE PAPA (Ou l'accompagnant) :**")
            poids_config["v_monnaie"] = st.checkbox("De la monnaie ou carte bancaire (pour la machine à café de la maternité)", value=poids_config.get("v_monnaie", False), key="v_m3")
            poids_config["v_snack"] = st.checkbox("Snacks, barres de céréales, gâteaux et boissons (le travail peut être long)", value=poids_config.get("v_snack", False), key="v_sn3")
            poids_config["v_chargeur"] = st.checkbox("Chargeurs de téléphone portables (avec un câble long si possible)", value=poids_config.get("v_chargeur", False), key="v_ch3")
            poids_config["v_rechange"] = st.checkbox("1 ou 2 t-shirts de rechange et une petite trousse de toilette de secours", value=poids_config.get("v_rechange", False), key="v_re3")
            poids_config["v_occu"] = st.checkbox("Lecture, écouteurs ou de quoi s'occuper pendant les heures d'attente", value=poids_config.get("v_occu", False), key="v_oc3")
       
        # --- VIGILANCE GROSSESSE À RISQUE ---
        st.write("### 🩺 Mon Accompagnement Première Grossesse & Vigilance")
        grossesse_risque = st.checkbox("⚠️ Activer le suivi : Grossesse à risque", value=poids_config.get("grossesse_risque", False), key="t2_risque_checkbox")
        if grossesse_risque:
            st.warning("🛑 **Protocole Vigilance Activé : Spécial SOPK & Résistance à l'insuline.**")
            with st.expander("🚨 ALERTE ROUGE : Quand consulter immédiatement les urgences maternité ?"):
                st.markdown("* **🩸 Saignements vaginaux**\n* **⚡ Contractions utérines douloureuses et régulières**\n* **🫨 Signes de Tension Élevée (Pré-éclampsie)**")

        if st.button("💾 Sauvegarder mon dossier complet", key="btn_save_info_bebe_complet"):
            poids_config["grossesse_risque"] = grossesse_risque
            supabase.table("config_grossesse").upsert({"id": 1, "config": json.dumps(poids_config)}).execute()
            st.success("🎉 Données cloud mémorisées !")
            redemarrer()

        # CALENDRIER EXAMENS REPOSITIONNÉ SANS LIMITATION
        st.write("### 📅 Mon Calendrier de Suivi Médical & Démarches")
        echo_datation_deb = date_debut_sa + timedelta(days=49)
        echo_datation_fin = date_debut_sa + timedelta(days=69)
        echo1_debut = date_debut_sa + timedelta(days=77)
        echo1_fin = date_debut_sa + timedelta(days=97)
        echo2_debut = date_debut_sa + timedelta(days=140)
        echo2_fin = date_debut_sa + timedelta(days=174)
        echo3_debut = date_debut_sa + timedelta(days=210)
        echo3_fin = date_debut_sa + timedelta(days=244)
        
        st.markdown(f"""
        * **🩺 De 7 à 10 SA (Du {echo_datation_deb.strftime('%d/%m/%Y')} au {echo_datation_fin.strftime('%d/%m/%Y')}) :** Échographie de datation.
        * **📋 Avant 14 SA (Du {echo1_debut.strftime('%d/%m/%Y')} au {echo1_fin.strftime('%d/%m/%Y')}) :** **Échographie T1 (Obligatoire)** + Déclaration CAF/CPAM.
        * **🩸 Chaque mois :** Prise de sang Toxoplasmose + Analyse d'urine complète (Albuminurie / Glycosurie).
        * **🩺 De 20 à 24 SA (Du {echo2_debut.strftime('%d/%m/%Y')} au {echo2_fin.strftime('%d/%m/%Y')}) :** **Échographie T2 Morphologique**.
        * **🧪 De 24 à 28 SA (Du {(date_debut_sa + timedelta(days=168)).strftime('%d/%m/%Y')} au {(date_debut_sa + timedelta(days=196)).strftime('%d/%m/%Y')}) :** **Test du Diabète Gestationnel (HGPO)**.
        * **🩺 De 30 à 34 SA (Du {echo3_debut.strftime('%d/%m/%Y')} au {echo3_fin.strftime('%d/%m/%Y')}) :** **Échographie T3 de Croissance**.
        * **🏥 Au 8ème mois :** Consultation d'anesthésie pour la péridurale.
        """)

    elif parcours_mode == "Parcours PMA (Procréation Médicalement Assistée)":
        st.subheader("Mon Carnet de Bord de Protocole PMA")
        pma_date_click = st.date_input("🗓️ Date du contrôle / injection", value=date.today(), key="t2_pma_date_click")
        col_p1, col_p2 = st.columns(2)
        with col_p1: pma_etape = st.selectbox("Étape :", ["Blocage ovarien", "Stimulation folliculaire", "Déclenchement", "Ponction", "Transfert d'embryon", "Attente Prise de Sang"], key="t2_pma_etape_sel")
        with col_p2: pma_med = st.text_input("Médicament / Dose (ex: Gonal 150 UI)", key="t2_pma_med_txt")
        pma_echo = st.text_input("Résultats Échographie / Prise de sang", key="t2_pma_echo_txt")
        pma_notes = st.text_input("Symptômes et consignes", key="t2_pma_notes_txt")
        if st.button("💾 Enregistrer cette étape PMA", key="btn_submit_pma_direct"):
            row_pma = {"Date": str(pma_date_click), "Étape Protocole": pma_etape, "Médicament / Injection": pma_med, "Résultats Échographie": pma_echo, "Notes & Symptômes": pma_notes}
            save_row_to_supabase("suivi_pma", row_pma)
            st.success("🧬 Étape PMA enregistrée !")
            redemarrer()

        st.write("---")
        carnet_pma()

# --- TAB 3 : RDV MEDICAUX ---
with tab3:
    st.subheader("📅 Gestion de tes Rendez-vous")

    st.write("### 📞 RDV à reprendre")
    st.caption("Les rendez-vous que tu dois encore prendre (kiné, échographie cardiaque...). Une étape à la fois.")
    rp1, rp2 = st.columns(2)
    with rp1:
        rp_spec = st.selectbox("Spécialité", ["Kiné", "Échographie cardiaque / cardiologue", "Gynécologue / équipe PMA", "Endocrinologue / diabétologue", "Médecin traitant", "Autre"], key="t3_rp_spec")
    with rp2:
        rp_tel = st.text_input("Téléphone (facultatif)", key="t3_rp_tel")
    rp_autre = st.text_input("Précise la spécialité", key="t3_rp_autre") if rp_spec == "Autre" else ""
    rp_pourquoi = st.text_input("Pour quoi ? (ordonnance, contrôle...)", key="t3_rp_pourquoi")
    if st.button("➕ Ajouter à ma liste", key="t3_rp_add"):
        spec_finale = rp_autre.strip() if rp_spec == "Autre" and rp_autre.strip() else rp_spec
        if save_row_to_supabase("rdv_a_prendre", {"Spécialité": spec_finale, "Pour quoi": rp_pourquoi, "Téléphone": rp_tel, "Statut": "À appeler", "Date appel": "", "Note": ""}):
            redemarrer()
    if not rdv_prendre_df.empty:
        st.caption("Change « Statut » dans le tableau : À appeler, Appelé, RDV pris, Fait. Quand le RDV est pris, ajoute-le plus bas dans « Gestion de tes Rendez-vous ».")
        editeur_table(rdv_prendre_df, "rdv_a_prendre", "ed_rdvp", choix={"Statut": ["À appeler", "Appelé", "RDV pris", "Fait"]})
        bloc_suppression(rdv_prendre_df, "rdv_a_prendre", "t3_rp_del", ["Spécialité", "Pour quoi"])
    st.write("---")
    col_r1, col_r2 = st.columns(2)
    with col_r1: rdv_date = st.date_input("Date du RDV", value=date.today(), key="t3_date")
    with col_r2: rdv_time = st.text_input("Heure", placeholder="14:30", key="t3_time")
    rdv_doc = st.text_input("Médecin / Spécialité", placeholder="Gynécologue", key="t3_doc")
    rdv_place = st.text_input("🏢 Lieu / Adresse du RDV", placeholder="Clinique...", key="t3_place")
    if st.button("📌 Ajouter ce rendez-vous", key="t3_submit_direct"):
        row_r = {"Date": str(rdv_date), "Heure": rdv_time, "Médecin / Spécialité": rdv_doc, "Lieu": rdv_place, "Notes": ""}
        if save_row_to_supabase("rdv_medicaux", row_r):
            st.success("🎉 Rendez-vous ajouté au Cloud !")
            redemarrer()
    if not rdv_df.empty:
        # NOUVEAU : statut + compte-rendu
        rdv_aff = rdv_df.copy()
        if "Statut" not in rdv_aff.columns:
            rdv_aff["Statut"] = "À venir"
        rdv_aff["Statut"] = rdv_aff["Statut"].fillna("À venir").replace("", "À venir")
        if "Compte-rendu" not in rdv_aff.columns:
            rdv_aff["Compte-rendu"] = ""
        rdv_aff = rdv_aff.sort_values(by="Date").reset_index(drop=True)
        st.dataframe(rdv_aff, use_container_width=True)

        st.write("**✅ Mon rendez-vous a eu lieu ?**")
        if "id" in rdv_aff.columns:
            a_valider = rdv_aff[rdv_aff["Statut"] != "✅ Effectué"]
            if a_valider.empty:
                st.caption("Tous tes rendez-vous sont marqués comme effectués.")
            else:
                opts_v = {f"{r['Date']} - {r['Médecin / Spécialité']} (n°{r['id']})": r["id"] for _, r in a_valider.iterrows()}
                v_choisi = st.selectbox("Quel rendez-vous ?", list(opts_v.keys()), key="t3_done_select")
                id_v = opts_v[v_choisi]
                eu_lieu = st.checkbox("✅ Le rendez-vous a eu lieu", key=f"t3_eu_lieu_{id_v}")
                compte_rendu = st.text_area("📝 Comment ça s'est passé ? (ce que le médecin a dit, examens, ordonnance, prochain RDV...)", key=f"t3_cr_{id_v}")
                if st.button("💾 Enregistrer le compte-rendu", key="t3_done_btn"):
                    if not eu_lieu:
                        st.warning("Coche d'abord « Le rendez-vous a eu lieu ».")
                    else:
                        try:
                            supabase.table("rdv_medicaux").update({"Statut": "✅ Effectué", "Compte-rendu": compte_rendu}).eq("id", int(id_v)).execute()
                            st.success("Rendez-vous marqué comme effectué !")
                            redemarrer()
                        except Exception as e:
                            st.error("Erreur : " + str(e))

        st.write("**✏️ Modifier un rendez-vous (en cas d'erreur)**")
        if "id" in rdv_aff.columns:
            def _txt(v):
                return "" if pd.isna(v) else str(v)

            opts_mod = {f"{r['Date']} - {r['Médecin / Spécialité']} (n°{r['id']})": r["id"] for _, r in rdv_aff.iterrows()}
            mod_choisi = st.selectbox("Quel rendez-vous corriger ?", list(opts_mod.keys()), key="t3_mod_select")
            id_mod = opts_mod[mod_choisi]
            ligne_mod = rdv_aff[rdv_aff["id"] == id_mod].iloc[0]
            try:
                date_mod_defaut = datetime.strptime(str(ligne_mod["Date"]), "%Y-%m-%d").date()
            except Exception:
                date_mod_defaut = date.today()
            mc1, mc2 = st.columns(2)
            with mc1:
                new_date = st.date_input("Date du RDV", value=date_mod_defaut, key=f"t3_mod_date_{id_mod}")
            with mc2:
                new_heure = st.text_input("Heure", value=_txt(ligne_mod.get("Heure")), key=f"t3_mod_heure_{id_mod}")
            new_doc = st.text_input("Médecin / Spécialité", value=_txt(ligne_mod.get("Médecin / Spécialité")), key=f"t3_mod_doc_{id_mod}")
            new_lieu = st.text_input("Lieu / Adresse", value=_txt(ligne_mod.get("Lieu")), key=f"t3_mod_lieu_{id_mod}")
            new_notes = st.text_input("Notes", value=_txt(ligne_mod.get("Notes")), key=f"t3_mod_notes_{id_mod}")
            statuts = ["À venir", "✅ Effectué", "❌ Annulé"]
            statut_actuel = _txt(ligne_mod.get("Statut"))
            new_statut = st.selectbox("Statut", statuts, index=statuts.index(statut_actuel) if statut_actuel in statuts else 0, key=f"t3_mod_statut_{id_mod}")
            new_cr = st.text_area("Compte-rendu", value=_txt(ligne_mod.get("Compte-rendu")), key=f"t3_mod_cr_{id_mod}")
            if st.button("💾 Enregistrer la correction", key="t3_mod_btn"):
                try:
                    supabase.table("rdv_medicaux").update({
                        "Date": str(new_date), "Heure": new_heure, "Médecin / Spécialité": new_doc,
                        "Lieu": new_lieu, "Notes": new_notes, "Statut": new_statut, "Compte-rendu": new_cr
                    }).eq("id", int(id_mod)).execute()
                    st.success("Rendez-vous corrigé !")
                    redemarrer()
                except Exception as e:
                    st.error("Erreur : " + str(e))

        st.write("**🗑️ Supprimer un rendez-vous**")
        options_rdv = {f"{r['Date']} - {r['Médecin / Spécialité']} (n°{r['id']})": r['id'] for _, r in rdv_df.iterrows()}
        rdv_choisi = st.selectbox("Choisir le rendez-vous à supprimer", list(options_rdv.keys()), key="t3_del_select")
        if st.button("🚨 Supprimer ce rendez-vous", key="t3_del_btn"):
            try:
                supabase.table("rdv_medicaux").delete().eq("id", options_rdv[rdv_choisi]).execute()
                st.success("Rendez-vous supprimé !")
                redemarrer()
            except Exception as e:
                st.error(f"Erreur de suppression : {e}")

    with st.expander("🧳 Préparer mon rendez-vous (questions, documents, besoins)"):
        st.write("**🎒 À emporter :**")
        for i_doc, doc_txt in enumerate(["Carte vitale et carte de mutuelle", "Ordonnances et liste de mes traitements", "Derniers résultats (prises de sang, échographies, comptes rendus)", "Ma fiche pour les médecins (onglet Fiche pour mes médecins)", "Mon carnet de glycémie et de température", "De l'eau, une collation et mon téléphone chargé"]):
            st.checkbox(doc_txt, key="t3_prep_" + str(i_doc))
        besoins_prep = charger_config(4).get("besoins", "")
        if besoins_prep:
            st.write("**🗣️ Ce que je veux dire au médecin :**")
            st.info(besoins_prep)
        else:
            st.caption("Écris tes besoins pour les consultations dans l'onglet « Fiche pour mes médecins » : ils s'afficheront ici.")
        st.write("---")
        bloc_questions("t3")

# --- TAB 4 : SUIVI NUTRITION ---
with tab4:
    st.subheader("🥗 Mon Suivi Métabolique")
    # ---------- STOCK MATÉRIEL GLYCÉMIE ----------
    st.write("### 🧰 Mon matériel de glycémie")
    materiel = {"bandelettes": 0, "aiguilles": 0, "seuil": 10}
    try:
        rep_mat = supabase.table("config_grossesse").select("*").eq("id", 3).execute()
        if rep_mat.data:
            cfg_mat = rep_mat.data[0]["config"]
            if isinstance(cfg_mat, str):
                cfg_mat = json.loads(cfg_mat)
            materiel.update(cfg_mat)
    except Exception:
        pass

    nb_bandelettes = int(materiel.get("bandelettes", 0))
    nb_aiguilles = int(materiel.get("aiguilles", 0))
    seuil_mat = int(materiel.get("seuil", 10))

    if nb_bandelettes == 0:
        st.error("🚨 Plus de bandelettes ! Il faut en racheter tout de suite.")
    elif nb_bandelettes <= seuil_mat:
        st.warning("⚠️ Bandelettes presque épuisées : il en reste " + str(nb_bandelettes) + ". Pense à en racheter (ordonnance à renouveler si besoin).")
    else:
        st.success("📦 Bandelettes : " + str(nb_bandelettes) + " restantes.")

    if nb_aiguilles == 0:
        st.error("🚨 Plus d'aiguilles (lancettes) ! Il faut en racheter tout de suite.")
    elif nb_aiguilles <= seuil_mat:
        st.warning("⚠️ Aiguilles presque épuisées : il en reste " + str(nb_aiguilles) + ". Pense à en racheter.")
    else:
        st.success("📦 Aiguilles : " + str(nb_aiguilles) + " restantes.")

    with st.expander("✏️ Modifier mon stock de matériel"):
        cm1, cm2, cm3 = st.columns(3)
        with cm1:
            new_band = st.number_input("Bandelettes", min_value=0, value=nb_bandelettes, step=1, key="t4_mat_band_" + str(nb_bandelettes))
        with cm2:
            new_aig = st.number_input("Aiguilles", min_value=0, value=nb_aiguilles, step=1, key="t4_mat_aig_" + str(nb_aiguilles))
        with cm3:
            new_seuil = st.number_input("Alerte quand il reste", min_value=1, value=seuil_mat, step=1, key="t4_mat_seuil_" + str(seuil_mat))
        if st.button("💾 Enregistrer mon matériel", key="t4_save_materiel"):
            try:
                supabase.table("config_grossesse").upsert({"id": 3, "config": {"bandelettes": int(new_band), "aiguilles": int(new_aig), "seuil": int(new_seuil)}}).execute()
                st.success("🎉 Matériel enregistré !")
                redemarrer()
            except Exception as e:
                st.error("Erreur d'enregistrement : " + str(e))

    st.write("---")
    # ---------- GLYCÉMIE ----------
    st.write("### 🩸 Ma glycémie")
    enceinte = st.checkbox("🤰 Je suis enceinte (objectifs de grossesse)", value=(parcours_mode == "Suivi de Grossesse Évolutif"), key="t4_enceinte")
    g_date = st.date_input("🗓️ Date de la mesure", value=date.today(), max_value=date.today(), key="t4_g_date")
    cg1, cg2 = st.columns(2)
    with cg1:
        glyc_val = st.number_input("Sucre (g/L)", min_value=0.0, max_value=6.0, value=0.95, step=0.01, key="t4_g_val")
    with cg2:
        glyc_mode = st.selectbox("Moment", ["Matin à jeun", "2h après le petit-déjeuner", "2h après le déjeuner", "2h après le dîner", "1h après un mauvais résultat"], key="t4_g_moment")
    a_jeun = (glyc_mode == "Matin à jeun")
    recontrole_1h = (glyc_mode == "1h après un mauvais résultat")
    seuil_post = 1.40 if recontrole_1h else (1.20 if enceinte else 1.40)
    if recontrole_1h:
        st.info("🔁 Mesure faite 1 h après un mauvais résultat. Note ce que tu as fait entre les deux (marche, eau, repas) dans le champ « repas » si il apparaît.")
    if glyc_val < 0.70:
        st.error("🔻 Glycémie basse (hypoglycémie). Prends tout de suite 15 g de sucre (3 morceaux de sucre ou un demi-verre de jus), assieds-toi, puis recontrôle dans 15 minutes. Si elle reste basse ou si tu as des malaises (sueurs, tremblements, confusion), appelle ton médecin ou le 15.")
    elif a_jeun:
        seuil_ok = 0.95 if enceinte else 1.00
        if glyc_val < seuil_ok:
            st.success("✅ Bonne valeur à jeun. Continue : repas réguliers, légumes en premier, marche après les repas, eau.")
        elif glyc_val < 1.26:
            msg = "⚠️ Valeur un peu élevée à jeun. Bois un verre d'eau, évite les sucres rapides aujourd'hui, fais un petit-déjeuner avec protéines et fibres, et marche 10 à 15 min après les repas. Si cela se répète 2 à 3 jours, préviens ton médecin."
            if enceinte:
                msg = msg + " En grossesse, parles-en rapidement à ta sage-femme ou ton médecin."
            st.warning(msg)
        else:
            st.error("🛑 Valeur élevée à jeun. Refais le contrôle (mains propres et sèches). Si elle est confirmée, appelle ton médecin dans la journée. Si tu as une soif intense, des vomissements, une grande fatigue ou une respiration inhabituelle, appelle le 15 ou va aux urgences.")
    else:
        seuil_ok = seuil_post
        if glyc_val < seuil_ok:
            st.success("✅ Bonne valeur après repas. Continue : légumes en premier et petite marche après le repas.")
        elif glyc_val < 2.00:
            msg = "⚠️ Valeur un peu élevée après repas. Marche tranquillement 10 à 15 min, bois de l'eau, et note ce que tu as mangé. Au prochain repas : légumes d'abord, moins de féculents et pas de boisson sucrée. Si cela se répète, préviens ton médecin."
            if enceinte:
                msg = msg + " En grossesse, parles-en rapidement à ta sage-femme ou ton médecin."
            st.warning(msg)
        else:
            st.error("🛑 Valeur très élevée après repas. Hydrate-toi, évite tout sucre, refais un contrôle dans 1 heure. Contacte ton médecin dans la journée. En cas de malaise, soif intense ou vomissements, appelle le 15.")
    st.caption("Repères indicatifs, je ne remplace pas un médecin. Ton équipe médicale fixe tes objectifs personnels.")

    # NOUVEAU : seuils, malaise et contrôle de vérification
    seuil_haut = (0.95 if enceinte else 1.00) if a_jeun else seuil_post
    taux_eleve = glyc_val >= seuil_haut
    taux_bas = glyc_val < 0.70

    malaise = st.checkbox("🤒 Je ne me sens pas bien", key="t4_malaise")
    symptomes_malaise = []
    if malaise:
        symptomes_malaise = st.multiselect("Qu'est-ce que tu ressens ?", ["Soif intense", "Sueurs / tremblements", "Vertiges", "Nausées / vomissements", "Fatigue inhabituelle", "Vision floue", "Maux de tête", "Confusion", "Respiration inhabituelle"], key="t4_malaise_symp")
        st.warning("Préviens ton médecin ou ta sage-femme aujourd'hui. En cas de confusion, vomissements, soif intense, respiration inhabituelle ou malaise important : appelle le 15.")

    refait = False
    glyc_ctrl = glyc_val
    delai_ctrl = ""
    if taux_eleve or taux_bas or malaise:
        st.write("#### 🔁 Contrôle de vérification")
        st.caption("Lave-toi et sèche-toi bien les mains, puis refais une mesure sur un autre doigt.")
        refait = st.checkbox("J'ai refait un contrôle", key="t4_refait")
        if refait:
            cv1, cv2 = st.columns(2)
            with cv1:
                glyc_ctrl = st.number_input("Valeur du contrôle (g/L)", min_value=0.0, max_value=6.0, value=float(glyc_val), step=0.01, key="t4_ctrl_val")
            with cv2:
                delai_ctrl = st.selectbox("Délai après la 1re mesure", ["Tout de suite", "15 minutes", "1 heure", "2 heures"], key="t4_ctrl_delai")
            if glyc_ctrl < 0.70:
                st.error("🔻 Toujours basse : reprends 15 g de sucre et recontrôle dans 15 min. Si ça ne remonte pas, appelle le 15.")
            elif taux_bas:
                st.success("✅ Ta glycémie est remontée. Mange une collation avec des féculents et surveille-toi.")
            elif glyc_ctrl >= seuil_haut:
                st.error("🛑 Valeur élevée confirmée. Contacte ton médecin dans la journée (ta sage-femme si tu es enceinte).")
            else:
                st.success("✅ Le contrôle est dans les repères : la 1re mesure était peut-être faussée (mains sales ou sucrées). Garde les deux valeurs et surveille.")

    repas_mange = ""
    seuil_repas = seuil_post
    if (not a_jeun) and glyc_val >= seuil_repas:
        repas_mange = st.text_input("🍽️ Qu'as-tu mangé à ce repas ? (pour comprendre ce qui fait monter)", key="t4_g_repas")
    if st.button("💾 Sauvegarder la glycémie", key="t4_submit_glyc_only"):
        txt_g = str(glyc_val) + " g/L"
        row_g = {
            "Date": str(g_date),
            "Glycémie à jeun": txt_g if a_jeun else "-",
            "Glycémie Post-Prandiale": "-" if a_jeun else txt_g,
            "Moment": glyc_mode,
            "Repas mangé": repas_mange,
            "Contrôle de vérification": (str(glyc_ctrl) + " g/L (" + delai_ctrl + ")") if refait else "",
            "Malaise": "Oui" if malaise else "Non",
            "Symptômes Malaise": ", ".join(symptomes_malaise)
        }
        if save_row_to_supabase("suivi_glycemie", row_g):
            try:
                nb_conso = 2 if refait else 1
                materiel["bandelettes"] = max(0, nb_bandelettes - nb_conso)
                materiel["aiguilles"] = max(0, nb_aiguilles - nb_conso)
                supabase.table("config_grossesse").upsert({"id": 3, "config": materiel}).execute()
            except Exception:
                pass
            st.success("🎉 Taux enregistré !")
            redemarrer()

    if not glyc_df_local.empty:
        st.write("**📈 Mon historique de glycémie**")
        g_df = glyc_df_local.copy().sort_values(by="Date").reset_index(drop=True)
        g_chart = pd.DataFrame({"Date": g_df["Date"]})
        g_chart["À jeun"] = pd.to_numeric(g_df["Glycémie à jeun"].astype(str).str.replace(" g/L", "", regex=False), errors="coerce")
        g_chart["Après repas"] = pd.to_numeric(g_df["Glycémie Post-Prandiale"].astype(str).str.replace(" g/L", "", regex=False), errors="coerce")
        st.line_chart(g_chart.set_index("Date"))
        st.dataframe(g_df, use_container_width=True)

        # --- NOUVEAU : moyenne par semaine ---
        g_sem = g_chart.copy()
        g_sem["Semaine"] = g_sem["Date"].apply(lundi_de)
        g_sem = g_sem[g_sem["Semaine"] != ""]
        if not g_sem.empty:
            seuil_j = 0.95 if enceinte else 1.00
            seuil_p = 1.20 if enceinte else 1.40
            g_sem["jeun_haut"] = (g_sem["À jeun"] >= seuil_j).astype(int)
            g_sem["post_haut"] = (g_sem["Après repas"] >= seuil_p).astype(int)
            resume_g = g_sem.groupby("Semaine", as_index=False).agg(moy_jeun=("À jeun", "mean"), moy_post=("Après repas", "mean"), haut_jeun=("jeun_haut", "sum"), haut_post=("post_haut", "sum"))
            resume_g["moy_jeun"] = resume_g["moy_jeun"].round(2)
            resume_g["moy_post"] = resume_g["moy_post"].round(2)
            resume_g["Semaine"] = resume_g["Semaine"].apply(lambda s: "Sem. du " + datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m"))
            resume_g = resume_g.rename(columns={"moy_jeun": "Moyenne à jeun (g/L)", "moy_post": "Moyenne après repas (g/L)", "haut_jeun": "Valeurs hautes à jeun", "haut_post": "Valeurs hautes après repas"})
            st.write("**🗓️ Ma glycémie semaine par semaine**")
            st.dataframe(resume_g.iloc[::-1].reset_index(drop=True), use_container_width=True)
            st.caption("Repères indicatifs. Montre ce tableau à ton médecin : la tendance compte plus qu'une valeur isolée.")

        if "id" in glyc_df_local.columns:
            opts_g = {}
            for _, r in glyc_df_local.iterrows():
                opts_g[str(r["Date"]) + " (n°" + str(r["id"]) + ")"] = r["id"]
            g_choisi = st.selectbox("Supprimer une mesure", list(opts_g.keys()), key="t4_del_g_select")
            if st.button("🚨 Supprimer cette mesure", key="t4_del_g_btn"):
                try:
                    supabase.table("suivi_glycemie").delete().eq("id", int(opts_g[g_choisi])).execute()
                    redemarrer()
                except Exception as e:
                    st.error("Erreur de suppression : " + str(e))

    st.write("---")

    # ---------- POIDS ----------
    st.write("### ⚖️ Mon poids")
    with st.expander("⚖️ Voir / masquer le détail de mon poids", expanded=not masquer_poids):

        poids_defaut = 70.0
        taille_defaut = 165
        p_df = pd.DataFrame()
        if not poids_df_local.empty:
            p_df = poids_df_local.copy()
            p_df["Poids (kg)"] = pd.to_numeric(p_df["Poids (kg)"], errors="coerce")
            p_df = p_df.dropna(subset=["Poids (kg)"]).sort_values(by="Date").reset_index(drop=True)
            if not p_df.empty:
                poids_defaut = float(p_df["Poids (kg)"].iloc[-1])
                try:
                    taille_defaut = int(float(p_df["Taille (cm)"].dropna().iloc[-1]))
                except Exception:
                    taille_defaut = 165

        p_date = st.date_input("🗓️ Date de la pesée", value=date.today(), max_value=date.today(), key="t4_p_date")
        cp1, cp2 = st.columns(2)
        with cp1:
            poids_val = st.number_input("Poids (kg)", min_value=30.0, max_value=200.0, value=poids_defaut, step=0.1, key="t4_poids_val")
        with cp2:
            taille_val = st.number_input("Taille (cm)", min_value=120, max_value=220, value=taille_defaut, step=1, key="t4_taille_val")

        tour_taille_val = st.number_input("Tour de taille (cm, facultatif, 0 = non mesuré)", min_value=0.0, max_value=200.0, value=0.0, step=0.5, key="t4_tour_taille")
        imc = poids_val / ((taille_val / 100) ** 2)
        st.caption("IMC pour ce poids : " + str(round(imc, 1)))
        contexte_poids = st.multiselect("Contexte de la pesée (pour comprendre les variations)", ["Avant / pendant les règles", "Rétention d'eau (jambes, mains, ventre gonflés)", "Repas salé ou restaurant la veille", "Mal dormi", "Traitement oublié", "Constipation", "Après un écart alimentaire"], key="t4_poids_ctx")
        note_poids_libre = st.text_input("Note (facultatif)", key="t4_poids_note")
        parts_note = []
        if contexte_poids:
            parts_note.append(", ".join(contexte_poids))
        if note_poids_libre:
            parts_note.append(note_poids_libre)
        note_poids = " | ".join(parts_note)

        if st.button("💾 Sauvegarder ma pesée", key="t4_submit_poids"):
            row_p = {"Date": str(p_date), "Poids (kg)": poids_val, "Note": note_poids, "Taille (cm)": int(taille_val), "Tour de taille (cm)": (tour_taille_val if tour_taille_val > 0 else None)}
            if save_row_to_supabase("suivi_poids", row_p):
                st.success("🎉 Pesée enregistrée !")
                redemarrer()

        if not p_df.empty:
            poids_depart = float(p_df["Poids (kg)"].iloc[0])
            poids_actuel = float(p_df["Poids (kg)"].iloc[-1])
            perdu = poids_depart - poids_actuel
            m1, m2, m3 = st.columns(3)
            m1.metric("Poids de départ", str(round(poids_depart, 1)) + " kg")
            m2.metric("Poids actuel", str(round(poids_actuel, 1)) + " kg")
            if perdu >= 0:
                m3.metric("Kilos perdus", str(round(perdu, 1)) + " kg")
            else:
                m3.metric("Kilos pris", str(round(abs(perdu), 1)) + " kg")
            st.caption("Départ : pesée du " + str(p_df["Date"].iloc[0]) + ". Dernière pesée : " + str(p_df["Date"].iloc[-1]) + ".")

            cfg_obj = charger_config(5)
            objectif_enreg = float(cfg_obj.get("objectif_poids", 0) or 0)
            st.write("**🎯 Mon objectif de poids** (à fixer avec ton médecin ou ton équipe PMA)")
            oc1, oc2 = st.columns(2)
            with oc1:
                obj_val = st.number_input("Objectif (kg), 0 = pas d'objectif", min_value=0.0, max_value=200.0, value=objectif_enreg, step=0.5, key="t4_obj_poids_" + str(objectif_enreg))
            with oc2:
                st.write("")
                if st.button("💾 Enregistrer mon objectif", key="t4_obj_save"):
                    if sauver_config(5, {"objectif_poids": float(obj_val)}):
                        redemarrer()
            if objectif_enreg > 0 and poids_depart > objectif_enreg:
                progression = min(1.0, max(0.0, (poids_depart - poids_actuel) / (poids_depart - objectif_enreg)))
                st.progress(progression)
                st.caption("Progression vers ton objectif : " + str(int(progression * 100)) + " %. Une perte douce et régulière suffit : le bon rythme est celui que ton équipe médicale te conseille.")

            import altair as alt
            p_df["Date_dt"] = pd.to_datetime(p_df["Date"])
            p_df["Moyenne 7 jours"] = p_df.set_index("Date_dt")["Poids (kg)"].rolling("7D").mean().round(2).values

            # --- Alerte si prise de poids rapide ---
            date_derniere = p_df["Date_dt"].iloc[-1]
            alertes_poids = []
            for jours_fen, seuil_fen in [(7, 1.5), (14, 2.0)]:
                ancien = p_df[p_df["Date_dt"] <= date_derniere - timedelta(days=jours_fen)]
                if not ancien.empty:
                    diff_fen = poids_actuel - float(ancien["Poids (kg)"].iloc[-1])
                    if diff_fen >= seuil_fen:
                        alertes_poids.append((jours_fen, diff_fen))
            if alertes_poids:
                jours_a, diff_a = alertes_poids[-1]
                st.warning("📈 Tu as pris environ " + str(round(diff_a, 1)) + " kg en " + str(jours_a) + " jours. Ce n'est pas un échec : le poids varie beaucoup avec l'eau, le sel, le cycle, le sommeil, un traitement oublié ou la résistance à l'insuline. Regarde la ligne pointillée (moyenne 7 jours), remplis le contexte de tes pesées et tes cases du jour. Si ça continue, parles-en à ton médecin.")
                if enceinte:
                    st.error("🤰 En grossesse, une prise de poids rapide avec gonflement du visage ou des mains, maux de tête, troubles de la vue ou douleur sous les côtes peut être un signe de pré-éclampsie : appelle ta sage-femme ou le 15 le jour même.")

            base_p = alt.Chart(p_df)
            ligne_p = base_p.mark_line(point=True, color="#e377c2").encode(
                x=alt.X("Date_dt:T", title="Date"), y=alt.Y("Poids (kg):Q", scale=alt.Scale(zero=False)),
                tooltip=["Date", "Poids (kg)", "Moyenne 7 jours"]
            )
            ligne_moy = base_p.mark_line(color="#444444", strokeDash=[5, 3]).encode(
                x=alt.X("Date_dt:T"), y=alt.Y("Moyenne 7 jours:Q", scale=alt.Scale(zero=False))
            )
            graphique_poids = (ligne_p + ligne_moy).properties(width=450, height=220)
            st.altair_chart(graphique_poids, use_container_width=False)
            st.caption("Ligne rose = poids de chaque pesée. Ligne pointillée = moyenne sur 7 jours : c'est elle qui compte, le poids du jour bouge avec l'eau, le sel et le cycle.")

            st.write("**📅 Historique de mes pesées**")
            h_df = p_df.copy()
            h_df["Variation (kg)"] = h_df["Poids (kg)"].diff().round(1)
            h_df["Perdu depuis le début (kg)"] = (poids_depart - h_df["Poids (kg)"]).round(1)
            colonnes = [c for c in ["Date", "Poids (kg)", "Variation (kg)", "Perdu depuis le début (kg)", "Tour de taille (cm)", "Note"] if c in h_df.columns]
            st.dataframe(h_df[colonnes].iloc[::-1].reset_index(drop=True), use_container_width=True)

            if "id" in p_df.columns:
                opts_p = {}
                for _, r in p_df.iterrows():
                    opts_p[str(r["Date"]) + " - " + str(r["Poids (kg)"]) + " kg (n°" + str(r["id"]) + ")"] = r["id"]
                p_choisi = st.selectbox("Supprimer une pesée", list(opts_p.keys()), key="t4_del_p_select")
                if st.button("🚨 Supprimer cette pesée", key="t4_del_p_btn"):
                    try:
                        supabase.table("suivi_poids").delete().eq("id", int(opts_p[p_choisi])).execute()
                        redemarrer()
                    except Exception as e:
                        st.error("Erreur de suppression : " + str(e))

    st.write("---")

    # ---------- RÉSULTATS DE PRISES DE SANG ----------
    st.write("### 🧪 Mes résultats de prises de sang")
    st.caption("HbA1c, hormones, vitamines : note ici tes résultats pour les retrouver et voir l'évolution.")
    bb1, bb2 = st.columns(2)
    with bb1:
        b_date = st.date_input("🗓️ Date de la prise de sang", value=date.today(), max_value=date.today(), key="t4_b_date")
    with bb2:
        b_exam = st.selectbox("Examen", ["HbA1c", "Glycémie à jeun (labo)", "AMH", "FSH", "LH", "Œstradiol", "TSH", "Vitamine D", "Vitamine B12", "Ferritine", "Autre"], key="t4_b_exam")
    b_autre = st.text_input("Nom de l'examen", key="t4_b_autre") if b_exam == "Autre" else ""
    bb3, bb4 = st.columns(2)
    with bb3:
        b_val = st.number_input("Valeur", value=0.0, step=0.1, format="%.2f", key="t4_b_val")
    with bb4:
        b_unite = st.text_input("Unité (ex : %, g/L, ng/mL)", key="t4_b_unite")
    b_note = st.text_input("Note (facultatif)", key="t4_b_note")
    if st.button("💾 Enregistrer ce résultat", key="t4_b_save"):
        nom_b = b_autre.strip() if b_exam == "Autre" and b_autre.strip() else b_exam
        if save_row_to_supabase("resultats_bilans", {"Date": str(b_date), "Examen": nom_b, "Valeur": b_val, "Unité": b_unite, "Note": b_note}):
            redemarrer()
    if not bilans_df.empty and "Examen" in bilans_df.columns:
        liste_exam = sorted(set(bilans_df["Examen"].astype(str).tolist()))
        voir_exam = st.selectbox("Voir l'évolution de :", liste_exam, key="t4_b_voir")
        sel_b = bilans_df[bilans_df["Examen"].astype(str) == voir_exam].copy()
        sel_b["Valeur"] = pd.to_numeric(sel_b["Valeur"], errors="coerce")
        sel_b = sel_b.dropna(subset=["Valeur"]).sort_values(by="Date")
        if len(sel_b) >= 2:
            st.line_chart(sel_b.set_index("Date")["Valeur"])
        st.dataframe(sel_b.drop(columns=[c for c in ["id", "created_at"] if c in sel_b.columns]).iloc[::-1].reset_index(drop=True), use_container_width=True)

    st.write("---")

    # ---------- QUAND FAIRE LA GLYCÉMIE + CONSEILS ----------
    st.write("### 🩸 Quand faire ma glycémie ?")
    with st.expander("📅 Repères pré-diabète et grossesse", expanded=True):
        st.markdown("""
**En pré-diabète (hors grossesse)**
* En général, pas besoin de se piquer tous les jours, sauf si ton médecin te le demande.
* Prise de sang à jeun et HbA1c : le plus souvent **1 fois par an**, ou tous les 3 à 6 mois si ton médecin le décide.
* Si tu fais des contrôles à la maison : **le matin à jeun**, ou **2 h après le début du repas**, jamais juste après avoir mangé.
* À jeun : moins de 1,00 g/L = normal. De 1,00 à 1,25 g/L = pré-diabète. À partir de 1,26 g/L (confirmé) = diabète.

**Si tu es enceinte (SOPK et pré-diabète = facteurs de risque)**
* Une glycémie à jeun est souvent demandée **dès le début de grossesse**.
* Le test **HGPO (boisson sucrée)** se fait entre **24 et 28 SA**, parfois plus tôt.
* Si un diabète gestationnel est confirmé : mesures **à jeun** et **1 h ou 2 h après les repas**, selon ton équipe.
* Objectifs fréquents : à jeun moins de 0,95 g/L, 2 h après repas moins de 1,20 g/L.

**Consulte sans attendre :** soif intense, urines très fréquentes, fatigue inhabituelle, vision floue, ou glycémie très élevée.
        """)

    with st.expander("🥦 Conseils nutrition (SOPK et résistance à l'insuline)"):
        st.markdown("""
* Commence le repas par les **légumes** et les fibres, puis les protéines, puis les féculents.
* **3 repas réguliers**, sans en sauter. Collation si besoin.
* Féculents **complets** en portion modérée.
* Évite les boissons sucrées et les jus : bois de l'**eau** (environ 1,5 L par jour).
* Associe un aliment sucré à des protéines ou des fibres (fruit + amandes, yaourt + fruits rouges).
* Limite les produits ultra-transformés et les sucres cachés.
* En grossesse : pas de viande, poisson ou œuf **cru ou peu cuit**, pas de fromage au lait cru, pas d'alcool.
        """)

    with st.expander("🚶 Sport et marche"):
        st.markdown("""
* **Marche 10 à 15 minutes après chaque repas** : très efficace contre les pics de glycémie.
* Objectif : environ **150 minutes par semaine** d'activité modérée, à adapter à tes douleurs et ta fatigue.
* **2 séances par semaine** de renforcement musculaire léger.
* Évite de rester assise plus d'1 h d'affilée.
* Avec la fibromyalgie : **commence doucement, augmente progressivement**, alterne effort et repos.
* En grossesse : sport doux (marche, natation, aquagym, yoga prénatal). **Arrête et consulte** en cas de saignements, douleurs, contractions, vertiges ou essoufflement anormal.
        """)

    with st.expander("🧘 Kiné et fibromyalgie"):
        st.markdown("""
* **Kiné** : séances régulières de mobilisation douce, d'étirements et de massage adapté aux zones douloureuses.
* **Activité physique adaptée** : marche, vélo doux, natation ou balnéothérapie (l'eau chaude soulage souvent).
* **Gestion de l'énergie** : fractionne tes activités, fais des pauses avant d'être épuisée, évite le « tout ou rien » les bons jours.
* **Chaleur** : bouillotte, douche chaude ou bain pour détendre les muscles.
* **Étirements et respiration** : 5 à 10 minutes par jour, cohérence cardiaque.
* **Sommeil** : horaires réguliers, 7 à 9 h. Un mauvais sommeil augmente la douleur, la fatigue et la glycémie.
* **Jours de crise** : réduis l'effort, reste active en douceur (courte marche, étirements) plutôt que de rester allongée toute la journée.
* Parles-en à ton médecin ou ton kiné pour un programme adapté, surtout en grossesse.
        """)

    st.write("---")
    st.write("### ✅ Mes conseils : fait ou pas fait ?")

    c_date = st.date_input("🗓️ Jour à remplir", value=date.today(), max_value=date.today(), key="t4_chk_date")
    jour_txt = str(c_date)

    tous_jours = {}
    try:
        rep_c = supabase.table("config_grossesse").select("*").eq("id", 2).execute()
        if rep_c.data:
            cfg_c = rep_c.data[0]["config"]
            if isinstance(cfg_c, str):
                cfg_c = json.loads(cfg_c)
            tous_jours = cfg_c.get("jours", {})
    except Exception:
        tous_jours = {}
    coches_sauvees = tous_jours.get(jour_txt, {})

    groupes = {
        "🥗 Nutrition": [
            ("n1", "J'ai commencé mes repas par les légumes"),
            ("n2", "J'ai fait 3 repas réguliers"),
            ("n3", "Pas de boisson sucrée aujourd'hui"),
            ("n4", "Féculents complets en portion modérée"),
            ("n5", "J'ai pris une collation équilibrée (fruit + protéines)"),
        ],
        "🚶 Sport et marche": [
            ("s1", "Marche de 10 à 15 min après le repas"),
            ("s2", "Activité modérée adaptée à mes douleurs"),
            ("s3", "Renforcement musculaire léger (2 fois par semaine)"),
            ("s4", "Je me suis levée régulièrement (pas assise 1 h d'affilée)"),
        ],
        "🧘 Kiné et fibromyalgie": [
            ("k1", "Séance de kiné ou exercices du kiné"),
            ("k2", "Étirements doux 5 à 10 minutes"),
            ("k3", "Chaleur (bouillotte, douche ou bain chaud)"),
            ("k4", "J'ai fait des pauses et géré mon énergie"),
            ("k5", "Respiration ou relaxation 5 minutes"),
            ("k6", "Bonne nuit de sommeil (7 à 9 h)"),
        ],
        "💧 Autres": [
            ("a1", "J'ai bu environ 1,5 L d'eau"),
            ("a2", "J'ai mesuré ma glycémie (si demandé par mon médecin)"),
            ("a3", "J'ai pris mon traitement et mes vitamines prescrites"),
        ],
    }

    etat = {}
    for titre_groupe, items_groupe in groupes.items():
        st.write("**" + titre_groupe + "**")
        for cle, texte in items_groupe:
            etat[cle] = st.checkbox(texte, value=bool(coches_sauvees.get(cle, False)), key="t4_chk_" + cle + "_" + jour_txt)

    nb_faits = sum(1 for v in etat.values() if v)
    nb_total = len(etat)
    st.progress(nb_faits / nb_total)
    st.caption(str(nb_faits) + " conseil(s) faits sur " + str(nb_total) + " le " + jour_txt)

    if st.button("💾 Enregistrer mes cases", key="t4_save_chk"):
        try:
            tous_jours[jour_txt] = etat
            supabase.table("config_grossesse").upsert({"id": 2, "config": {"jours": tous_jours}}).execute()
            st.success("🎉 Cases enregistrées pour le " + jour_txt + " !")
            redemarrer()
        except Exception as e:
            st.error("Erreur d'enregistrement : " + str(e))

    if tous_jours:
        st.write("**📊 Mes derniers jours**")
        lignes_h = []
        for d_txt in sorted(tous_jours.keys(), reverse=True)[:14]:
            lignes_h.append({"Date": d_txt, "Conseils faits": sum(1 for v in tous_jours[d_txt].values() if v), "Sur": nb_total})
        st.dataframe(pd.DataFrame(lignes_h), use_container_width=True)

    st.caption("Ces conseils sont généraux. Ton médecin, ta sage-femme, ton kiné ou ta diététicienne les adaptent à ton cas.")

    # ---------- BILAN PAR SEMAINE ----------
    st.write("---")
    st.write("### 🗓️ Mon bilan par semaine (poids, traitement, conseils)")
    if p_df.empty:
        st.caption("Enregistre quelques pesées pour voir ton bilan.")
    else:
        def _lundi(d_txt):
            try:
                d = datetime.strptime(str(d_txt), "%Y-%m-%d").date()
                return str(d - timedelta(days=d.weekday()))
            except Exception:
                return ""

        bil = p_df.copy()
        bil["Semaine"] = bil["Date"].apply(_lundi)
        bil = bil[bil["Semaine"] != ""]
        bilan = bil.groupby("Semaine", as_index=False)["Poids (kg)"].mean().rename(columns={"Poids (kg)": "Poids moyen (kg)"})
        bilan["Poids moyen (kg)"] = bilan["Poids moyen (kg)"].round(1)
        bilan["Variation (kg)"] = bilan["Poids moyen (kg)"].diff().round(1)

        jours_trait = {}
        if not history_df.empty and "Prise" in history_df.columns:
            ht = history_df[history_df["Prise"].astype(str) != "Aucune"]
            for d_txt in set(ht["Date"].tolist()):
                s_lundi = _lundi(d_txt)
                if s_lundi:
                    jours_trait[s_lundi] = jours_trait.get(s_lundi, 0) + 1

        conseils_sem = {}
        for d_txt, coches in tous_jours.items():
            s_lundi = _lundi(d_txt)
            if s_lundi:
                conseils_sem.setdefault(s_lundi, []).append(sum(1 for v in coches.values() if v))

        bilan["Jours avec traitement pris"] = bilan["Semaine"].apply(lambda s: jours_trait.get(s, 0))
        bilan["Conseils faits (moy./jour)"] = bilan["Semaine"].apply(lambda s: round(sum(conseils_sem[s]) / len(conseils_sem[s]), 1) if s in conseils_sem else None)
        bilan["Semaine"] = bilan["Semaine"].apply(lambda s: "Sem. du " + datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m"))
        st.dataframe(bilan.iloc[::-1].reset_index(drop=True), use_container_width=True)
        st.caption("Regarde si les semaines où le poids monte sont celles où le traitement ou les conseils ont baissé. Ce tableau sert à comprendre, pas à te juger.")
# --- TAB 5 : HISTORIQUE DIRECT ---
with tab5:
    st.subheader("📜 Historique Général Cloud")
    st.write("**Mon journal de bord des prises du jour :**")
    if not history_df.empty:
        editeur_table(history_df, "historique_prises", "ed_hist")
        if "id" in history_df.columns:
            opts_h = {}
            for _, r in history_df.iterrows():
                opts_h[str(r["Date"]) + " - " + str(r["Médicament"]) + " - " + str(r["Prise"]) + " (n°" + str(r["id"]) + ")"] = r["id"]
            h_choisi = st.selectbox("Supprimer une ligne du journal", list(opts_h.keys()), key="t5_del_h_select")
            if st.button("🚨 Supprimer cette ligne", key="t5_del_h_btn"):
                try:
                    supabase.table("historique_prises").delete().eq("id", int(opts_h[h_choisi])).execute()
                    st.success("Ligne supprimée !")
                    redemarrer()
                except Exception as e:
                    st.error("Erreur de suppression : " + str(e))
    else:
        st.caption("Aucune prise de médicament enregistrée dans le Cloud pour le moment.")

    st.write("---")
    st.write("**Mon historique des températures :**")
    if not cycle_df.empty:
        editeur_table(cycle_df, "cycle_temperature", "ed_cycle")
        if "id" in cycle_df.columns:
            opts_t = {}
            for _, r in cycle_df.iterrows():
                opts_t[str(r["Date"]) + " - " + str(r["Température"]) + " °C (n°" + str(r["id"]) + ")"] = r["id"]
            t_choisi = st.selectbox("Supprimer une température", list(opts_t.keys()), key="t5_del_t_select")
            if st.button("🚨 Supprimer cette température", key="t5_del_t_btn"):
                try:
                    supabase.table("cycle_temperature").delete().eq("id", int(opts_t[t_choisi])).execute()
                    st.success("Température supprimée !")
                    redemarrer()
                except Exception as e:
                    st.error("Erreur de suppression : " + str(e))
    else:
        st.caption("Aucune température enregistrée dans le Cloud pour le moment.")

    # NOUVEAU : glycémie, poids et rendez-vous modifiables
    st.write("---")
    st.write("**Mon historique de glycémie (modifiable) :**")
    editeur_table(glyc_df_local, "suivi_glycemie", "ed_glyc")

    st.write("---")
    st.write("**Mon historique de poids (modifiable) :**")
    editeur_table(poids_df_local, "suivi_poids", "ed_poids")

    st.write("---")
    st.write("**Mes rendez-vous (modifiables, compte-rendu inclus) :**")
    editeur_table(rdv_df, "rdv_medicaux", "ed_rdv")

    st.write("---")
    st.write("**Mes tests d'ovulation (modifiables) :**")
    editeur_table(tests_df.drop(columns=[c for c in ["Photo"] if c in tests_df.columns]), "tests_ovulation", "ed_tests")


    st.write("---")
    st.write("**Mes douleur / fatigue / sommeil (modifiable) :**")
    editeur_table(douleur_df, "suivi_douleur_fatigue", "ed_douleur")
    bloc_suppression(douleur_df, "suivi_douleur_fatigue", "t5_douleur_del", ["Date", "Douleur (0-10)"])

    st.write("---")
    st.write("**Mes résultats de prises de sang (modifiable) :**")
    editeur_table(bilans_df, "resultats_bilans", "ed_bilans")
    bloc_suppression(bilans_df, "resultats_bilans", "t5_bilans_del", ["Date", "Examen", "Valeur"])

# --- TAB 6 : DOULEUR, FATIGUE, SOMMEIL ---
with tab6:
    st.subheader("🧘 Douleur, fatigue et sommeil")
    st.caption("Quelques secondes par jour. Ça aide tes médecins et ton kiné à voir ce qui change selon ton cycle, ton sommeil et tes efforts.")
    d_date = st.date_input("🗓️ Jour", value=date.today(), max_value=date.today(), key="t6_date")
    c61, c62 = st.columns(2)
    with c61:
        d_douleur = st.slider("Douleur (0 = aucune, 10 = insupportable)", 0, 10, 3, key="t6_douleur")
        d_fatigue = st.slider("Fatigue (0 = en forme, 10 = épuisée)", 0, 10, 4, key="t6_fatigue")
    with c62:
        d_heures = st.number_input("Heures de sommeil", min_value=0.0, max_value=16.0, value=7.0, step=0.5, key="t6_heures")
        d_qualite = st.slider("Qualité du sommeil (0 = très mauvais, 10 = très bon)", 0, 10, 5, key="t6_qualite")
    d_zones = st.multiselect("Où as-tu mal ? (fibromyalgie)", ["Nuque", "Épaules", "Dos", "Hanches", "Bras", "Mains", "Jambes", "Pieds", "Tête"], key="t6_zones")
    d_endo = st.multiselect("Symptômes d'endométriose aujourd'hui", ["Douleurs pelviennes", "Règles douloureuses", "Douleurs pendant les rapports", "Douleurs en allant à la selle", "Douleurs urinaires", "Ballonnements importants", "Douleurs dans le dos / les jambes"], key="t6_endo")
    d_note = st.text_input("Note (facultatif)", key="t6_note")
    if d_douleur >= 8:
        st.warning("Douleur très forte : repose-toi, utilise la chaleur, et préviens ton médecin si ça dure ou si c'est nouveau.")
    st.caption("Douleur dans la poitrine, essoufflement inhabituel ou malaise : appelle le 15.")
    if st.button("💾 Enregistrer ce jour", key="t6_save"):
        row_d = {"Date": str(d_date), "Douleur (0-10)": d_douleur, "Fatigue (0-10)": d_fatigue, "Sommeil (h)": d_heures, "Qualité sommeil (0-10)": d_qualite, "Zones douloureuses": ", ".join(d_zones), "Symptômes endométriose": ", ".join(d_endo), "Note": d_note}
        if save_row_to_supabase("suivi_douleur_fatigue", row_d):
            st.success("🎉 Enregistré !")
            redemarrer()

    if not douleur_df.empty:
        dd = douleur_df.copy()
        cols_m = [c for c in ["Douleur (0-10)", "Fatigue (0-10)", "Qualité sommeil (0-10)", "Sommeil (h)"] if c in dd.columns]
        for c in cols_m:
            dd[c] = pd.to_numeric(dd[c], errors="coerce")
        dd["Date_dt"] = pd.to_datetime(dd["Date"], errors="coerce")
        dd = dd.dropna(subset=["Date_dt"])
        if not dd.empty and cols_m:
            jour_moy = dd.groupby("Date_dt", as_index=False)[cols_m].mean()
            aujourdhui = pd.Timestamp(date.today())
            sem1 = jour_moy[jour_moy["Date_dt"] > aujourdhui - pd.Timedelta(days=7)]
            sem0 = jour_moy[(jour_moy["Date_dt"] <= aujourdhui - pd.Timedelta(days=7)) & (jour_moy["Date_dt"] > aujourdhui - pd.Timedelta(days=14))]
            st.write("**📊 Cette semaine comparée à la précédente**")
            mcols = st.columns(3)
            for colw, (lib, c, inverse) in zip(mcols, [("Douleur", "Douleur (0-10)", True), ("Fatigue", "Fatigue (0-10)", True), ("Sommeil (h)", "Sommeil (h)", False)]):
                if c in jour_moy.columns and not sem1.empty and not pd.isna(sem1[c].mean()):
                    moy1 = float(sem1[c].mean())
                    delta_val = None
                    if not sem0.empty and not pd.isna(sem0[c].mean()):
                        delta_val = round(moy1 - float(sem0[c].mean()), 1)
                    colw.metric(lib, str(round(moy1, 1)), delta=delta_val, delta_color="inverse" if inverse else "normal")

            mesures = [c for c in ["Douleur (0-10)", "Fatigue (0-10)", "Qualité sommeil (0-10)"] if c in jour_moy.columns]
            if mesures:
                import altair as alt
                long_d = jour_moy.melt(id_vars="Date_dt", value_vars=mesures, var_name="Mesure", value_name="Valeur").dropna(subset=["Valeur"])
                lignes_d = alt.Chart(long_d).mark_line(point=True).encode(
                    x=alt.X("Date_dt:T", title="Date"), y=alt.Y("Valeur:Q", title="0 à 10", scale=alt.Scale(domain=[0, 10])),
                    color=alt.Color("Mesure:N", legend=alt.Legend(orient="bottom")), tooltip=["Date_dt", "Mesure", "Valeur"]
                )
                regles_d = []
                if not cycle_df.empty and "Cycle Status" in cycle_df.columns:
                    regles_d = sorted(set(cycle_df[cycle_df["Cycle Status"] == "🩸 Début des Règles"]["Date"].tolist()))
                graph_d = lignes_d
                if regles_d:
                    regles_df_d = pd.DataFrame({"Date_dt": pd.to_datetime(regles_d)})
                    graph_d = lignes_d + alt.Chart(regles_df_d).mark_rule(color="red", strokeDash=[4, 4]).encode(x="Date_dt:T")
                st.altair_chart(graph_d.properties(width=450, height=260), use_container_width=False)
                st.caption("Traits rouges = début de tes règles : regarde si la douleur ou la fatigue montent à certains moments du cycle.")

        st.write("**📋 Mes 14 derniers enregistrements**")
        st.dataframe(douleur_df.sort_values(by="Date", ascending=False).head(14).drop(columns=[c for c in ["created_at"] if c in douleur_df.columns]), use_container_width=True)
    else:
        st.caption("Aucun enregistrement pour le moment.")

# --- TAB 7 : FICHE POUR MES MÉDECINS ---
with tab7:
    st.subheader("📄 Fiche pour mes médecins")
    st.caption("Un résumé à montrer ou à imprimer avant un rendez-vous. Remplis une fois les 4 champs, le reste se met à jour tout seul.")
    cfg_f = charger_config(4)
    f_diag = st.text_area("🩺 Mes diagnostics et antécédents", value=cfg_f.get("diagnostics", ""), key="t7_diag", placeholder="Écris ici ce que tu veux que tes médecins voient en premier.")
    f_allerg = st.text_input("⚠️ Allergies / intolérances", value=cfg_f.get("allergies", ""), key="t7_allerg")
    f_besoins = st.text_area("🗣️ Mes besoins pour les consultations", value=cfg_f.get("besoins", ""), key="t7_besoins", placeholder="Ex : m'expliquer chaque geste avant l'examen, me prévenir avant de me toucher, me laisser des pauses, me donner les consignes par écrit.")
    f_contact = st.text_input("👤 Personne de confiance / accompagnant", value=cfg_f.get("contact", ""), key="t7_contact")
    if st.button("💾 Enregistrer ces informations", key="t7_save"):
        if sauver_config(4, {"diagnostics": f_diag, "allergies": f_allerg, "besoins": f_besoins, "contact": f_contact}):
            st.success("🎉 Informations enregistrées !")
            redemarrer()

    def _une_ligne(t):
        return " / ".join(x.strip() for x in str(t).splitlines() if x.strip())

    fiche = []
    infos = []
    if f_diag.strip():
        infos.append("Diagnostics et antécédents : " + _une_ligne(f_diag))
    if f_allerg.strip():
        infos.append("Allergies / intolérances : " + _une_ligne(f_allerg))
    if f_besoins.strip():
        infos.append("Mes besoins pour la consultation : " + _une_ligne(f_besoins))
    if f_contact.strip():
        infos.append("Personne de confiance : " + _une_ligne(f_contact))
    if infos:
        fiche.append(("👤 À savoir en premier", infos))

    lig_t = []
    for nom_m, info_m3 in meds.items():
        moments_m = [lib for lib, cle, defaut in MOMENTS_PRISE if info_m3.get(cle, defaut)]
        lig_t.append(nom_m + " : " + " / ".join(moments_m) + ", " + str(dose_actuelle_med(info_m3)) + " cachet(s) par prise (" + str(info_m3.get("timing", "")) + ")")
    fiche.append(("💊 Traitements actuels", lig_t or ["Aucun traitement enregistré"]))

    lig_g = []
    if not glyc_df_local.empty and all(c in glyc_df_local.columns for c in ["Glycémie à jeun", "Glycémie Post-Prandiale"]):
        gg = glyc_df_local.copy()
        gg["jeun"] = pd.to_numeric(gg["Glycémie à jeun"].astype(str).str.replace(" g/L", "", regex=False), errors="coerce")
        gg["post"] = pd.to_numeric(gg["Glycémie Post-Prandiale"].astype(str).str.replace(" g/L", "", regex=False), errors="coerce")
        gg = gg[gg["Date"] >= str(date.today() - timedelta(days=14))]
        for lib_g, col_g in [("À jeun", "jeun"), ("Après repas", "post")]:
            v_g = gg[col_g].dropna()
            if len(v_g) > 0:
                lig_g.append(lib_g + " (14 derniers jours) : " + str(len(v_g)) + " mesure(s), moyenne " + str(round(float(v_g.mean()), 2)) + " g/L, de " + str(round(float(v_g.min()), 2)) + " à " + str(round(float(v_g.max()), 2)) + " g/L")
    if not bilans_df.empty and "Examen" in bilans_df.columns:
        for ex_b in sorted(set(bilans_df["Examen"].astype(str).tolist())):
            sel_f = bilans_df[bilans_df["Examen"].astype(str) == ex_b].sort_values(by="Date")
            dern = sel_f.iloc[-1]
            lig_g.append("Dernier résultat " + ex_b + " : " + str(dern.get("Valeur", "")) + " " + ("" if pd.isna(dern.get("Unité", "")) else str(dern.get("Unité", ""))) + " (" + str(dern["Date"]) + ")")
    fiche.append(("🩸 Glycémie et prises de sang", lig_g or ["Pas de donnée récente"]))

    lig_p = []
    if not poids_df_local.empty:
        pp = poids_df_local.copy()
        pp["Poids (kg)"] = pd.to_numeric(pp["Poids (kg)"], errors="coerce")
        pp = pp.dropna(subset=["Poids (kg)"]).sort_values(by="Date")
        if not pp.empty:
            actuel_f = float(pp["Poids (kg)"].iloc[-1])
            depart_f = float(pp["Poids (kg)"].iloc[0])
            lig_p.append("Poids actuel : " + str(round(actuel_f, 1)) + " kg (pesée du " + str(pp["Date"].iloc[-1]) + "), poids de départ : " + str(round(depart_f, 1)) + " kg")
            ancien_f = pp[pp["Date"] <= str(date.today() - timedelta(days=28))]
            if not ancien_f.empty:
                var_f = actuel_f - float(ancien_f["Poids (kg)"].iloc[-1])
                lig_p.append("Variation depuis environ 4 semaines : " + ("+" if var_f >= 0 else "") + str(round(var_f, 1)) + " kg")
    fiche.append(("⚖️ Poids", lig_p or ["Pas de pesée enregistrée"]))

    lig_c = []
    regles_f = []
    if not cycle_df.empty and "Cycle Status" in cycle_df.columns:
        regles_f = sorted(set(cycle_df[cycle_df["Cycle Status"] == "🩸 Début des Règles"]["Date"].tolist()))
    if regles_f:
        lig_c.append("Dernières règles : " + datetime.strptime(regles_f[-1], "%Y-%m-%d").strftime("%d/%m/%Y"))
        durees_f = []
        for a_f, b_f in zip(regles_f[:-1], regles_f[1:]):
            dif_f = (datetime.strptime(b_f, "%Y-%m-%d").date() - datetime.strptime(a_f, "%Y-%m-%d").date()).days
            if 15 <= dif_f <= 90:
                durees_f.append(dif_f)
        if durees_f:
            lig_c.append("Durée moyenne des cycles : " + str(int(round(sum(durees_f) / len(durees_f)))) + " jours (sur " + str(len(durees_f)) + " cycle(s))")
    if not tests_df.empty and "Résultat" in tests_df.columns:
        pics_f = tests_df[tests_df["Résultat"].astype(str).str.startswith("🥚 Pic")]
        txt_pic = ""
        if not pics_f.empty:
            txt_pic = ", dernier pic le " + str(pics_f["Date"].max())
        lig_c.append("Tests d'ovulation : " + str(len(tests_df)) + " enregistré(s), " + str(len(pics_f)) + " pic(s)" + txt_pic)
    fiche.append(("🌸 Cycle et ovulation", lig_c or ["Pas de donnée de cycle"]))

    lig_d = []
    if not douleur_df.empty:
        dd7 = douleur_df.copy()
        dd7 = dd7[dd7["Date"] >= str(date.today() - timedelta(days=14))]
        for lib_d, col_d in [("Douleur", "Douleur (0-10)"), ("Fatigue", "Fatigue (0-10)"), ("Sommeil (h)", "Sommeil (h)")]:
            if col_d in dd7.columns:
                v_d = pd.to_numeric(dd7[col_d], errors="coerce").dropna()
                if len(v_d) > 0:
                    lig_d.append(lib_d + " (moyenne sur 14 jours) : " + str(round(float(v_d.mean()), 1)) + " sur " + str(len(v_d)) + " jour(s) noté(s)")
    fiche.append(("🧘 Douleur, fatigue, sommeil", lig_d or ["Pas de donnée récente"]))

    lig_r = []
    if not rdv_df.empty and "Date" in rdv_df.columns:
        for _, r_f in rdv_df.sort_values(by="Date").iterrows():
            if str(r_f["Date"]) >= str(date.today()) and str(r_f.get("Statut", "")) != "✅ Effectué":
                lig_r.append("Rendez-vous le " + str(r_f["Date"]) + " : " + str(r_f.get("Médecin / Spécialité", "")))
    if not rdv_prendre_df.empty and "Statut" in rdv_prendre_df.columns:
        for _, r_p in rdv_prendre_df[rdv_prendre_df["Statut"] != "Fait"].iterrows():
            lig_r.append("À prendre : " + str(r_p.get("Spécialité", "")) + " (" + str(r_p.get("Statut", "")) + ")")
    fiche.append(("📅 Rendez-vous", lig_r or ["Aucun rendez-vous à venir"]))

    lig_pma = []
    if not examens_df.empty and "Examen" in examens_df.columns:
        for _, r_e in examens_df.sort_values(by="Date").iterrows():
            lig_pma.append(str(r_e["Date"]) + " : " + str(r_e["Examen"]) + " (" + str(r_e.get("Statut", "")) + ")")
    if lig_pma:
        fiche.append(("🧬 Examens PMA", lig_pma))

    lig_q = []
    if not questions_df.empty and "Question" in questions_df.columns and "Posée" in questions_df.columns:
        for _, r_q in questions_df[questions_df["Posée"].astype(str) != "Oui"].iterrows():
            lig_q.append(str(r_q["Question"]) + " (" + str(r_q.get("Pour", "")) + ")")
    fiche.append(("❓ Mes questions à poser", lig_q or ["Aucune question en attente"]))

    st.write("---")
    st.write("### 📋 Mon résumé")
    for titre_f, lignes_f in fiche:
        st.write("**" + titre_f + "**")
        for l_f in lignes_f:
            st.write("• " + l_f)

    import html as html_lib
    corps_html = ""
    corps_txt = "FICHE POUR MES MÉDECINS - éditée le " + date.today().strftime("%d/%m/%Y") + "\n"
    for titre_f, lignes_f in fiche:
        corps_html += "<h3>" + html_lib.escape(titre_f) + "</h3><ul>" + "".join("<li>" + html_lib.escape(l_f) + "</li>" for l_f in lignes_f) + "</ul>"
        corps_txt += "\n" + titre_f + "\n" + "\n".join("- " + l_f for l_f in lignes_f) + "\n"
    page_html = "<html><head><meta charset='utf-8'><title>Fiche pour mes médecins</title><style>body{font-family:Arial,sans-serif;max-width:800px;margin:20px auto;line-height:1.5} h3{border-bottom:1px solid #ccc;padding-bottom:4px}</style></head><body><h2>Fiche pour mes médecins</h2><p>Éditée le " + date.today().strftime("%d/%m/%Y") + "</p>" + corps_html + "</body></html>"
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button("⬇️ Fiche à imprimer (ouvre-la puis Imprimer, Enregistrer en PDF)", data=page_html.encode("utf-8"), file_name="fiche_medecins_" + str(date.today()) + ".html", mime="text/html", key="t7_dl_html")
    with dl2:
        st.download_button("⬇️ Version texte", data=corps_txt.encode("utf-8"), file_name="fiche_medecins_" + str(date.today()) + ".txt", mime="text/plain", key="t7_dl_txt")
    st.caption("Ces informations viennent de ce que tu as noté dans l'appli. Elles ne remplacent pas un dossier médical.")
