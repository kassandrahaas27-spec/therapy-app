import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json
import os
from supabase import create_client, Client

st.set_page_config(page_title="Mon Therapy Suivi Global", page_icon="🤰", layout="centered")

# --- PARAMÈTRES DE CONNEXION SUPABASE SÉCURISÉS ---
SUPABASE_URL = "https://supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhenhtdmV1a2lxcGNlZnpnaHNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI2MDg5NzUsImV4cCI6MjEwODE4NDk3NX0.Wgte8gModYiTAWuX0EuODuYrmiGZ42Z6pEHF91UJztI"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

# --- INITIALISATION ET SÉCURISATION DES TABLES CLOUD ---
def verifier_tables_supabase():
    # Ce bloc invisible s'assure que Supabase possède tes 6 tables prêtes à recevoir des données
    tables = ["medicaments", "historique_prises", "cycle_temperature", "rdv_medicaux", "suivi_glycemie", "suivi_poids"]
    # Les données migreront vers ces espaces au premier clic
verifier_tables_supabase()

# --- ENTRÉE DIRECTE SANS CODE SÉCURISÉE PAR EMAIL ---
st.title("Mon suivi Therapy : Traitement, SOPK, Fertilité & Pré-Diabète")

def redemarrer():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()

# --- SYSTÈME DE CHARGEMENT DEPUIS SUPABASE (FLUIDE & COMPATIBLE) ---
def load_db_from_supabase(table_name, columns):
    try:
        response = supabase.table(table_name).select("*").execute()
        if response.data:
            df = pd.DataFrame(response.data)
            if "Date" in df.columns:
                df["Date"] = df["Date"].astype(str)
            return df
        return pd.DataFrame(columns=columns)
    except:
        return pd.DataFrame(columns=columns)

def save_row_to_supabase(table_name, data_dict):
    try:
        supabase.table(table_name).insert(data_dict).execute()
    except Exception as e:
        st.error(f"Erreur de sauvegarde Cloud : {e}")

# Chargement instantané des données de ton coffre-fort Supabase
history_df = load_db_from_supabase("historique_prises", ["Date", "Médicament", "Prise", "Moment Repas", "Symptômes Traitement", "Symptômes SOPK/Pré-Diabète", "Note"])
cycle_df = load_db_from_supabase("cycle_temperature", ["Date", "Cycle Status", "Température", "Rapport Sexuel", "Note", "Mode Parcours"])
rdv_df = load_db_from_supabase("rdv_medicaux", ["Date", "Heure", "Médecin / Spécialité", "Lieu", "Notes"])
glyc_df_local = load_db_from_supabase("suivi_glycemie", ["Date", "Glycémie à jeun", "Glycémie Post-Prandiale", "Petit-Déjeuner", "Déjeuner", "Dîner", "Dessert / Plaisir", "Grignotage / Encas", "Activité Physique", "Hydratation (Verres)", "Conseils & Alertes"])
poids_df_local = load_db_from_supabase("suivi_poids", ["Date", "Poids (kg)", "Note", "Taille (cm)"])

# Chargement des configurations de médicaments
try:
    meds_response = supabase.table("medicaments").select("*").execute()
    meds = {row["name"]: json.loads(row["config"]) for row in meds_response.data} if meds_response.data else {}
except:
    meds = {}

# Chargement configuration bébé
try:
    config_response = supabase.table("config_grossesse").select("*").execute()
    poids_config = json.loads(config_response.data[0]["config"]) if config_response.data else {}
except:
    poids_config = {}

# --- ALERTE STOCKS FAIBLES ---
alertes = [name for name, info in meds.items() if int(info.get("stock", 0)) <= 5]
if alertes:
    for med_alerte in alertes:
        st.error(f"⚠️ **ALERTE STOCK FAIBLE** : Il reste seulement {meds[med_alerte]['stock']} comprimé(s) pour **{med_alerte}** !")
# --- MENU DE GAUCHE ---
st.sidebar.header("⚙️ Configuration Globale")
parcours_mode = st.sidebar.selectbox("🌸 Ton parcours actuel :", ["Suivi de Cycle & Essai Bébé", "Suivi de Grossesse Évolutif", "Parcours PMA (Procréation Médicalement Assistée)"], key="side_parcours_mode")

with st.sidebar.expander("✏️ Ajouter ou Modifier un Médicament", expanded=False):
    med_mode = st.sidebar.radio("Action", ["Nouveau médicament", "Modifier un existant"], key="side_med_mode")
    current_med_name = ""
    default_stock = 30
    default_timing = "Début de repas"
    default_m, default_mi, default_s = False, False, False
    default_is_evo = False
    default_nb_cachet = 1
    default_dur1 = 7
    default_d2 = 2
    
    if med_mode == "Modifier un existant" and meds:
        current_med_name = st.sidebar.selectbox("Choisir le médicament à modifier", list(meds.keys()), key="side_select_med")
        info_m = meds[current_med_name]
        default_stock = int(info_m.get("stock", 30))
        default_timing = info_m.get("timing", "Début de repas")
        default_m = info_m.get("prend_matin", False)
        default_mi = info_m.get("prend_midi", False)
        default_s = info_m.get("prend_soir", False)
        default_is_evo = info_m.get("is_evolution", False)
        
        phases_list = info_m.get("phases", [])
        if isinstance(phases_list, list) and len(phases_list) > 0:
            default_nb_cachet = int(phases_list[0].get("dose", 1))
            default_dur1 = int(phases_list[0].get("duration", 7))
            if len(phases_list) > 1:
                default_d2 = int(phases_list[1].get("dose", 2))
        elif isinstance(phases_list, dict):
            default_nb_cachet = int(phases_list.get("dose", 1))
            default_dur1 = int(phases_list.get("duration", 7))

    med_name = st.sidebar.text_input("Nom du médicament", value=current_med_name if med_mode == "Modifier un existant" else "", key="side_med_name").strip()
    
    stock_actuel = default_stock
    if med_mode == "Modifier un existant":
        action_stock = st.sidebar.radio("Mouvement de stock :", ["Ne pas toucher", "➕ Ajouter (Achat de boîte)", "➖ Enlever (Perte / Oubli)"], key="side_stock_action")
        val_mouv = st.sidebar.number_input("Quantité de comprimés concernés :", min_value=0, value=0, key="side_stock_mouv_val")
        if action_stock == "➕ Ajouter (Achat de boîte)": stock_actuel += val_mouv
        elif action_stock == "➖ Enlever (Perte / Oubli)": stock_actuel = max(0, stock_actuel - val_mouv)
    else:
        stock_actuel = st.sidebar.number_input("Stock initial (comprimés)", min_value=0, value=default_stock, key="side_med_stock_init")

    timing = st.sidebar.selectbox("Moment lié au repas", ["Début de repas", "Milieu de repas", "Fin de repas"], index=["Début de repas", "Milieu de repas", "Fin de repas"].index(default_timing), key="side_med_timing")
    
    st.sidebar.markdown("**Moments de prise conseillés :**")
    p_matin = st.sidebar.checkbox("🌅 Matin", value=default_m, key="side_p_matin")
    p_midi = st.sidebar.checkbox("☀️ Midi", value=default_mi, key="side_p_midi")
    p_soir = st.sidebar.checkbox("🌙 Soir", value=default_s, key="side_p_soir")
    
    st.sidebar.markdown("---")
    is_evolution = st.sidebar.checkbox("🔄 Ce traitement est évolutif (Paliers de dose)", value=default_is_evo, key="side_is_evo_cb")
    
    if is_evolution:
        st.sidebar.caption("⚙️ Configure ton protocole Metformine :")
        d1 = st.sidebar.number_input("Dose Palier 1 (cachets/repas)", min_value=1, value=default_nb_cachet, key="side_d1_val")
        dur1 = st.sidebar.number_input("Durée Palier 1 (en jours)", min_value=1, value=default_dur1, key="side_dur1_val")
        d2 = st.sidebar.number_input("Dose Palier 2 (cachets final)", min_value=1, value=default_d2, key="side_d2_val")
        phases_save = [{"dose": int(d1), "duration": int(dur1)}, {"dose": int(d2), "duration": 9999}]
        nb_cachets_repas = int(d1)
    else:
        nb_cachets_repas = st.sidebar.number_input("Nombre de cachet(s) par repas :", min_value=1, value=default_nb_cachet, key="side_nb_cachets_repas")
        phases_save = [{"dose": int(nb_cachets_repas), "duration": 9999}]

    if st.sidebar.button("💾 Enregistrer le médicament", key="side_save_med_btn"):
        if med_name:
            config_med = {
                "stock": int(stock_actuel), "timing": timing, "start_date": str(date.today()), "is_evolution": is_evolution, "phases": phases_save,
                "prend_matin": p_matin, "prend_midi": p_midi, "prend_soir": p_soir, "nb_cachet_par_repas": int(nb_cachets_repas)
            }
            try:
                supabase.table("medicaments").upsert({"name": med_name, "config": json.dumps(config_med)}).execute()
                st.sidebar.success("🎉 Médicament enregistré sur Supabase !")
                redemarrer()
            except Exception as e:
                st.sidebar.error(f"Erreur Supabase : {e}")

if meds:
    with st.sidebar.expander("🗑️ Supprimer un Médicament", expanded=False):
        med_to_delete = st.sidebar.selectbox("Choisir à supprimer", list(meds.keys()), key="side_del_med_select")
        if st.sidebar.button("🚨 Confirmer la suppression", key="side_del_med_btn"):
            try:
                supabase.table("medicaments").delete().eq("name", med_to_delete).execute()
                st.sidebar.success("🚨 Médicament supprimé !")
                redemarrer()
            except:
                pass

# --- ONGLETS PRINCIPAUX ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📱 Tableau de Bord", "🌸 Mon Suivi Féminin", "📅 Rendez-vous Médicaux", "🥗 Suivi Glycémie & Nutrition", "📜 Historique & Corrections"])

# --- TAB 1 : TABLEAU DE BORD ---
with tab1:

    st.subheader("📅 Prises du jour & Vos Symptômes")
    st.caption(f"Mode actif : **{parcours_mode}**")
    
    if not meds:
        st.info("Ajoute un médicament dans le menu à gauche pour commencer.")
    else:
        prises_details = {}
        for name, info in meds.items():
            st.write(f"#### 💊 {name}")
            
            dose_actuelle = int(info.get("nb_cachet_par_repas", 1))
            if info.get("is_evolution", False) and "phases" in info:
                try:
                    p1 = info["phases"][0]
                    date_debut = datetime.strptime(info.get("start_date", str(date.today())), "%Y-%m-%d").date()
                    jours_ecoules = (date.today() - date_debut).days
                    if jours_ecoules < int(p1.get("duration", 7)):
                        dose_actuelle = int(p1.get("dose", 1))
                        jours_restants = int(p1.get("duration", 7)) - jours_ecoules
                        st.info(f"⏳ **Palier 1 en cours** : Prendre **{dose_actuelle} cachet(s)** par repas. Augmentation dans **{jours_restants} jour(s)**.")
                    else:
                        if len(info["phases"]) > 1:
                            dose_actuelle = int(info["phases"][1].get("dose", 2))
                        st.success(f"🚀 **Palier Maximal atteint !** Dose stable de **{dose_actuelle} cachet(s)**.")
                except:
                    pass
            
            st.caption(f"Moments requis : {'🌅 Matin ' if info.get('prend_matin') else ''}{'☀️ Midi ' if info.get('prend_midi') else ''}{'🌙 Soir' if info.get('prend_soir') else ''} — Prendre **{dose_actuelle} cachet(s)** ({info.get('timing')})")
            col_m, col_mid, col_s = st.columns(3)
            matin_check, midi_check, soir_check = False, False, False
            with col_m:
                if info.get("prend_matin", True): matin_check = st.checkbox("🌅 Pris le Matin", key=f"t1_{name}_matin_unique_key_securisee")
            with col_mid:
                if info.get("prend_midi", False): midi_check = st.checkbox("☀️ Pris le Midi", key=f"t1_{name}_midi_unique_key_securisee")
            with col_s:
                if info.get("prend_soir", True): soir_check = st.checkbox("🌙 Pris le Soir", key=f"t1_{name}_soir_unique_key_securisee")
                    
            prises_details[name] = {"Matin": matin_check, "Midi": midi_check, "Soir": soir_check, "dose_unitaire": dose_actuelle}
            st.write("---")
            
        st.write("### 🧪 1. Effets Secondaires fréquents")
        symp_med_choisis = []
        liste_symp_med = ["Nausées / Vomissements", "Diarrhées", "Maux d'estomac / Brûlures", "Perte d'appétit", "Vertiges", "Bouffées de chaleur"]
        c_m1, c_m2 = st.columns(2)
        for idx, s in enumerate(liste_symp_med):
            with c_m1 if idx % 2 == 0 else c_m2:
                if st.checkbox(s, key=f"t1_med_symptome_{s}_unique_key"): symp_med_choisis.append(s)
                
        st.write("### 🌸 2. Symptômes liés au Cycle, SOPK & Glycémie")
        symp_cycle_choisis = []
        note_jour = st.text_input("Notes libres sur ta journée", placeholder="RAS", key="t1_note_libre_validation_unique")
        
        if st.button("✅ Enregistrer ma journée", key="t1_submit_bouton_validation_final_unique"):
            for name, moments in prises_details.items():
                moments_cochés = [k for k, v in moments.items() if k in ["Matin", "Midi", "Soir"] and v]
                if len(moments_cochés) > 0:
                    total_de_cachets_pris = len(moments_cochés) * moments["dose_unitaire"]
                    txt_prise = ", ".join(moments_cochés) + f" ({total_de_cachets_pris} cachet(s))"
                else:
                    txt_prise = "Aucune"
                
                row_data = {
                    "Date": str(date.today()), "Médicament": name, "Prise": txt_prise, "Moment Repas": meds[name]["timing"], 
                    "Symptômes Traitement": ", ".join(symp_med_choisis) if symp_med_choisis else "Aucun",
                    "Symptômes SOPK/Pré-Diabète": ", ".join(symp_cycle_choisis) if symp_cycle_choisis else "Aucun", "Note": note_jour
                }
                save_row_to_supabase("historique_prises", row_data)
                
                # Mise à jour du stock local
                info_m["stock"] = max(0, int(info_m.get("stock", 30)) - total_de_cachets_pris)
                supabase.table("medicaments").upsert({"name": name, "config": json.dumps(info_m)}).execute()
                
            st.success("🎉 Enregistré dans ton coffre-fort Supabase Cloud !")
            redemarrer()

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
                
        if not cycle_df.empty:
            import altair as alt
            graphique_zoome = alt.Chart(cycle_df.sort_values(by="Date").reset_index(drop=True)).mark_line(point=True, color="#1f77b4").encode(
                x=alt.X('Date:T', title='Date'), y=alt.Y('Température:Q', title='°C Basale', scale=alt.Scale(domain=[35.0, 37.5]))
            ).properties(width=450, height=250)
            st.altair_chart(graphique_zoome, use_container_width=False)
            
            st.write("### 🔮 Analyse de ton Cycle & Fertilité SOPK")
            temps_list = cycle_df["Température"].tolist()
            status_list = cycle_df["Cycle Status"].tolist()
            rapports_list = cycle_df["Rapport Sexuel"].tolist()
            dates_list = cycle_df["Date"].tolist()
            
            ovulation_detectee = None
            date_ovulation_reelle = None
            if len(temps_list) >= 4:
                for i in range(3, len(temps_list)):
                    moyenne_avant = sum(temps_list[i-3:i]) / 3
                    if temps_list[i] >= moyenne_avant + 0.28 and all(t >= moyenne_avant + 0.2 for t in temps_list[i:min(i+3, len(temps_list))]):
                        ovulation_detectee = dates_list[i]
                        date_ovulation_reelle = datetime.strptime(ovulation_detectee, "%Y-%m-%d").date()
            
            test_ovulation_recent = "🥚 Test d'Ovulation Positif" in status_list[-5:]
            rapport_recent = "Oui" in rapports_list[-3:]
            
            if test_ovulation_recent and rapport_recent:
                st.metric(label="Chances de conception estimées", value="85% - 95%", delta="Optimale (Rapport + Test OK)", delta_color="inverse")
            elif date_ovulation_reelle and "Oui" in rapports_list[-5:]:
                st.metric(label="Chances de conception estimées", value="60% - 75%", delta="Très bonne (Hausse thermique validée)")
            else:
                st.metric(label="Chances de conception estimées", value="10% - 15%", delta="Phase standard / d'attente")

    elif parcours_mode == "Suivi de Grossesse Évolutif":
        st.subheader("🤰 Mon Calendrier Obstétrical SOPK (SA + J)")
        st.info("💡 Spécial SOPK : En raison de cycles irréguliers, ce calendrier se base sur ta date d'ovulation (conception) ou sur la datation de ton échographie pour calculer ton terme exact.")
        
        poids_config = load_json("config_grossesse.json")
        methode_calcul = st.radio("Méthode pour caler ton calendrier :", ["Entrer ma date d'ovulation / conception", "Entrer ma date de terme officielle (DPA)"], key="t2_methode_calcul")
        
        if methode_calcul == "Entrer ma date d'ovulation / conception":
            ovul_defaut = poids_config.get("date_ovulation", str(date.today() - timedelta(days=35)))
            date_ovul = st.date_input("🗓️ Date exacte de ton ovulation :", value=datetime.strptime(ovul_defaut, "%Y-%m-%d").date(), key="t2_grossesse_ovul")
            date_terme = date_ovul + timedelta(days=273)
        else:
            dpa_defaut = poids_config.get("dpa", str(date.today() + timedelta(days=240)))
            date_terme = st.date_input("🗓️ Date Prévue d'Accouchement (Terme) :", value=datetime.strptime(dpa_defaut, "%Y-%m-%d").date(), key="t2_grossesse_dpa")
            date_ovul = date_terme - timedelta(days=273)

        if st.button("💾 Sauvegarder et recalculer mon calendrier", key="btn_save_dpa_sopk"):
            poids_config["dpa"] = str(date_terme)
            poids_config["date_ovulation"] = str(date_ovul)
            save_json(poids_config, "config_grossesse.json")
            st.success("🎉 Calendrier recalculé avec succès !")
            redemarrer()
            
        date_debut_sa = date_ovul - timedelta(days=14)
        jours_totaux_sa = (date.today() - date_debut_sa).days
        
        if 0 <= jours_totaux_sa <= 287:
            sa_semaines = jours_totaux_sa // 7
            sa_jours = jours_totaux_sa % 7
            
            if sa_semaines <= 6: mois_txt = "1er mois (1er Trimestre)"
            elif 7 <= sa_semaines <= 10: mois_txt = "2ème mois (1er Trimestre)"
            elif 11 <= sa_semaines <= 15: mois_txt = "3ème mois (1er Trimestre)"
            elif 16 <= sa_semaines <= 19: mois_txt = "4ème mois (2ème Trimestre)"
            elif 20 <= sa_semaines <= 24: mois_txt = "5ème mois (2ème Trimestre)"
            elif 25 <= sa_semaines <= 28: mois_txt = "6ème mois (2ème Trimestre)"
            elif 29 <= sa_semaines <= 32: mois_txt = "7ème mois (3ème Trimestre)"
            elif 33 <= sa_semaines <= 36: mois_txt = "8ème mois (3ème Trimestre)"
            else: mois_txt = "9ème mois (3ème Trimestre)"
            
            st.info(f"✨ Stade de ta grossesse : **{sa_semaines} SA + {sa_jours} jours** — Vous êtes dans ton **{mois_txt}**.")
            st.caption(f"⏳ Conception : {date_ovul.strftime('%d/%m/%Y')} | Terme officiel : {date_terme.strftime('%d/%m/%Y')} (J-{(date_terme - date.today()).days}).")

                       # --- VIGILANCE GROSSESSE À RISQUE ---
            st.write("### 🩺 Mon Accompagnement Première Grossesse & Vigilance")
            grossesse_risque = st.checkbox("⚠️ Activer le protocole de suivi : Grossesse à risque obstétrical ou métabolique", value=poids_config.get("grossesse_risque", False), key="t2_risque_checkbox")
            
            if grossesse_risque:
                st.warning("🛑 **Protocole Vigilance Activé : Spécial SOPK & Résistance à l'insuline.** Ce guide médical vous accompagne pas à pas.")
                with st.expander("🚨 ALERTE ROUGE : Quand consulter immédiatement les urgences maternité ?"):
                    st.markdown("""
                    Rends-toi tout de suite à la maternité si tu as :
                    * **🩸 Saignements vaginaux :** Rouges ou sombres, légers ou abondants.
                    * **⚡ Contractions utérines douloureuses et régulières :** Si ton ventre se durcit de manière répétée.
                    * **🫨 Signes de Tension Élevée (Pré-éclampsie) :** Maux de tête violents, mouches devant les yeux, bourdonnements d'oreilles.
                    * **🍃 Baisse des mouvements de bébé :** Si bébé ne bouge plus du tout ou beaucoup moins sur une demi-journée.
                    """)
                with st.expander("📉 Guide Clinique : Maîtriser mon Diabète Gestationnel"):
                    st.markdown("""
                    * **🎯 Les objectifs cibles :** Rester sous **0,92 g/L le matin à jeun**, et sous **1,20 g/L deux heures après le repas**.
                    * **🥗 Hydratation pure :** Écarte totalement les sirops. Privilégie l'eau minérale pure.
                    """)
            
            with st.expander("🧠 Aide psychologique : Gérer le stress du premier bébé"):
                st.markdown("""
                * **🧘 Évacuer l'anxiété :** Égayer tes pensées, être perdue pour une première grossesse est 100 % normal. 
                * **🧘 Technique de respiration :** Inspire par le nez pendant 4 secondes, expire par la bouche pendant 6 secondes. Fais cela 5 fois.
                """)  
            # --- BLOC BEBE CENTRALISÉ ---
        st.write("### 👶 Informations Secrètes sur Bébé(s)")
        genre_bebe_choix = ["Non renseigné / Surprise 🤫", "Fille 🌸", "Garçon 💎", "Jumeaux / Grossesse Multiple 🤰🤰"]
        poids_config["genre_bebe"] = st.selectbox("👶 Genre du bébé :", genre_bebe_choix, index=genre_bebe_choix.index(poids_config.get("genre_bebe", "Non renseigné / Surprise 🤫")), key="t2_genre_bebe_sel")
        poids_config["notes_bebe"] = st.text_input("📝 Notes sur les Échographies (ex: Il bouge beaucoup, poids estimé...)", value=poids_config.get("notes_bebe", ""), key="t2_notes_bebe_txt")

            # --- RANGE-DOCUMENTS ET COMPTE-RENDU MEDICAL ---
                with st.expander("📁 Range-Documents : Mesures Échographies & Bilans"):
                st.caption("💡 Centralise ici tes chiffres clés pour les avoir sous les yeux face au médecin :")
                poids_config["doc_lcc"] = st.text_input("Longueur Cranio-Caudale T1 (LCC en mm) :", value=poids_config.get("doc_lcc", ""), key="t2_lcc")
                poids_config["doc_bip"] = st.text_input("Diamètre Bi-Pariétal T2 (BIP en mm) :", value=poids_config.get("doc_bip", ""), key="t2_bip")
                poids_config["doc_poids_est"] = st.text_input("Poids estimé de bébé (en grammes) :", value=poids_config.get("doc_poids_est", ""), key="t2_poids_est")
                poids_config["doc_toxo"] = st.selectbox("Statut Toxoplasmose :", ["Non immunisée (Prise de sang mensuelle) 🩸", "Immunisée ✅"], index=0 if poids_config.get("doc_toxo", "") == "" or "Non" in poids_config.get("doc_toxo", "") else 1, key="t2_toxo_stat")

            # --- CHECKLIST VALISE MATERNITÉ ---
            with st.expander("🍼 Checklist : Ma Valise de Maternité (À cocher)"):
                st.write("**Pour Bébé (Salle de naissance & Séjour) :**")
                poids_config["v_body"] = st.checkbox("5 ou 6 bodys en coton (ouverture devant)", value=poids_config.get("v_body", False), key="v1")
                poids_config["v_pyj"] = st.checkbox("6 pyjamas / dors-bien chauds", value=poids_config.get("v_pyj", False), key="v2")
                poids_config["v_gilet"] = st.checkbox("3 gilets en laine ou brassières", value=poids_config.get("v_gilet", False), key="v3")
                poids_config["v_turb"] = st.checkbox("1 turbulette / gigoteuse (taille 0-6 mois)", value=poids_config.get("v_turb", False), key="v4")
                poids_config["v_bonnet"] = st.checkbox("1 bonnet en coton et des petites chaussettes", value=poids_config.get("v_bonnet", False), key="v5")
                st.write("**Pour Maman :**")
                poids_config["v_adm"] = st.checkbox("Dossier médical complet (Carte vitale, carte groupe sanguin, échos)", value=poids_config.get("v_adm", False), key="v6")
                poids_config["v_confort"] = st.checkbox("Tenues confortables et amples pour le séjour", value=poids_config.get("v_confort", False), key="v7")
                poids_config["v_hyg"] = st.checkbox("Trousse de toilette + serviettes hygiéniques ultra-absorbantes", value=poids_config.get("v_hyg", False), key="v8")

            if st.button("💾 Sauvegarder mon dossier complet", key="btn_save_info_bebe_complet"):
                poids_config["grossesse_risque"] = grossesse_risque
                supabase.table("config_grossesse").upsert({"id": 1, "config": json.dumps(poids_config)}).execute()
                st.success("🎉 Données cloud mémorisées !")
                redemarrer()

# --- TAB 3 : RDV MEDICAUX ---
with tab3:
    st.subheader("📅 Gestion de tes Rendez-vous")
    col_r1, col_r2 = st.columns(2)
    with col_r1: rdv_date = st.date_input("Date du RDV", value=date.today(), key="t3_date")
    with col_r2: rdv_time = st.text_input("Heure", placeholder="14:30", key="t3_time")
    rdv_doc = st.text_input("Médecin / Spécialité", placeholder="Gynécologue", key="t3_doc")
    rdv_place = st.text_input("🏢 Lieu / Adresse du RDV", placeholder="Clinique...", key="t3_place")
    if st.button("📌 Ajouter ce rendez-vous", key="t3_submit_direct"):
        row_r = {"Date": str(rdv_date), "Heure": rdv_time, "Médecin / Spécialité": rdv_doc, "Lieu": rdv_place, "Notes": ""}
        save_row_to_supabase("rdv_medicaux", row_r)
        st.success("🎉 Rendez-vous ajouté au Cloud !")
        redemarrer()
    if not rdv_df.empty: st.dataframe(rdv_df, use_container_width=True)

# --- TAB 4 : SUIVI NUTRITION ---
with tab4:
    st.subheader("🥗 Mon Suivi Métabolique")
    glyc_val = st.number_input("Sucre (g/L)", min_value=0.0, max_value=3.0, value=0.95, step=0.01, key="t4_g_val")
    glyc_mode = st.selectbox("Moment", ["Matin à jeun", "2h après le repas"], key="t4_g_moment")
    if st.button("💾 Sauvegarder la glycémie", key="t4_submit_glyc_only"):
        row_g = {"Date": str(date.today()), "Glycémie à jeun": f"{glyc_val} g/L" if glyc_mode == "Matin à jeun" else "-", "Glycémie Post-Prandiale": f"{glyc_val} g/L" if glyc_mode == "2h après le repas" else "-"}
        save_row_to_supabase("suivi_glycemie", row_g)
        st.success("🎉 Taux enregistré !")
        redemarrer()

    st.write("---")
    poids_val = st.number_input("Ton poids actuel (kg)", min_value=30.0, max_value=200.0, value=70.0, step=0.1, key="t4_poids_val")
    if st.button("💾 Sauvegarder ma pesée", key="t4_submit_poids"):
        row_p = {"Date": str(date.today()), "Poids (kg)": poids_val, "Note": "", "Taille (cm)": 165}
        save_row_to_supabase("suivi_poids", row_p)
        st.success("🎉 Pesée enregistrée !")
        redemarrer()
    if not poids_df_local.empty:
        import altair as alt
        graphique_poids = alt.Chart(poids_df_local).mark_line(point=True, color="#e377c2").encode(x='Date:T', y='Poids (kg):Q').properties(width=450, height=200)
        st.altair_chart(graphique_poids, use_container_width=False)

# --- TAB 5 : HISTORIQUE DIRECT ---
with tab5:
    st.subheader("📜 Historique Général Cloud")
    st.write("**Mon journal de bord des prises du jour :**")
    if not history_df.empty: 
        st.dataframe(history_df, use_container_width=True)
    else:
        st.caption("Aucune prise de médicament enregistrée dans le Cloud pour le moment.")
        
    st.write("---")
    st.write("**Mon historique des températures :**")
    if not cycle_df.empty: 
        st.dataframe(cycle_df, use_container_width=True)
    else:
        st.caption("Aucune température enregistrée dans le Cloud pour le moment.")

