import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json
import os

st.set_page_config(page_title="Mon Therapy Suivi Global", page_icon="🤰", layout="centered")

# --- ENTRÉE DIRECTE SANS CODE SÉCURISÉE PAR EMAIL ---
st.title("Mon suivi Therapy : Traitement, SOPK, Fertilité & Pré-Diabète")

MEDS_FILE = "medicaments.json"
HISTORY_FILE = "historique.json"
CYCLE_FILE = "cycle_temperature.json"
RDV_FILE = "rdv_medicaux.json"
GLYC_FILE = "suivi_glycemie.json"
POIDS_FILE = "suivi_poids.json"
PMA_FILE = "suivi_pma.json"

def redemarrer():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f: return json.load(f)
    return {}

def save_json(data, filename):
    with open(filename, "w") as f: json.dump(data, f, indent=4)

def load_df(filename, columns):
    if os.path.exists(filename):
        try:
            df = pd.read_json(filename)
            for col in columns:
                if col not in df.columns:
                    if col == "Rapport Sexuel": df[col] = "Non"
                    elif col in ["Glycémie à jeun", "Glycémie Post-Prandiale"]: df[col] = "-"
                    else: df[col] = "Non renseigné"
            if not df.empty and "Date" in df.columns:
                df["Date"] = df["Date"].astype(str)
            return df
        except:
            return pd.DataFrame(columns=columns)
    return pd.DataFrame(columns=columns)

def save_df(df, filename):
    if "Date" in df.columns:
        df["Date"] = df["Date"].astype(str)
    df.to_json(filename, date_format="iso")

meds = load_json(MEDS_FILE)
history_df = load_df(HISTORY_FILE, ["Date", "Médicament", "Prise", "Moment Repas", "Symptômes Traitement", "Symptômes SOPK/Pré-Diabète", "Note"])
cycle_df = load_df(CYCLE_FILE, ["Date", "Cycle Status", "Température", "Rapport Sexuel", "Note", "Mode Parcours"])
rdv_df = load_df(RDV_FILE, ["Date", "Heure", "Médecin / Spécialité", "Lieu", "Notes"])
glyc_df_local = load_df(GLYC_FILE, ["Date", "Glycémie à jeun", "Glycémie Post-Prandiale", "Petit-Déjeuner", "Déjeuner", "Dîner", "Dessert / Plaisir", "Grignotage / Encas", "Activité Physique", "Hydratation (Verres)", "Conseils & Alertes"])
poids_df_local = load_df(POIDS_FILE, ["Date", "Poids (kg)", "Note", "Taille (cm)"])
pma_df = load_df(PMA_FILE, ["Date", "Étape Protocole", "Médicament / Injection", "Résultats Échographie", "Notes & Symptômes"])

# --- ALERTE STOCKS FAIBLES ---
alertes = [name for name, info in meds.items() if int(info.get("stock", 0)) <= 5]
if alertes:
    for med_alerte in alertes:
        st.error(f"⚠️ **ALERTE STOCK FAIBLE** : Il reste seulement {meds[med_alerte]['stock']} comprimé(s) pour **{med_alerte}** !")
# --- MENU DE GAUCHE : CONFIGURATION ET PARCOURS ---
st.sidebar.header("⚙️ Configuration Globale")
parcours_mode = st.sidebar.selectbox("🌸 Ton parcours actuel :", ["Suivi de Cycle & Essai Bébé", "Suivi de Grossesse Évolutif", "Parcours PMA (Procréation Médicalement Assistée)"], key="side_parcours_mode")

with st.sidebar.expander("✏️ Ajouter ou Modifier un Médicament", expanded=False):
    med_mode = st.sidebar.radio("Action", ["Nouveau médicament", "Modifier un existant"], key="side_med_mode")
    current_med_name = ""
    default_stock = 30
    default_timing = "Début de repas"
    default_m = False
    default_mi = False
    default_s = False
    default_nb_cachet = 1
    
    if med_mode == "Modifier un existant" and meds:
        current_med_name = st.sidebar.selectbox("Choisir le médicament à modifier", list(meds.keys()), key="side_select_med")
        default_stock = int(meds[current_med_name].get("stock", 30))
        default_timing = meds[current_med_name].get("timing", "Début de repas")
        default_m = meds[current_med_name].get("prend_matin", False)
        default_mi = meds[current_med_name].get("prend_midi", False)
        default_s = meds[current_med_name].get("prend_soir", False)
        default_nb_cachet = meds[current_med_name].get("nb_cachet_par_repas", 1)
    
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
    nb_cachets_repas = st.sidebar.number_input("Nombre de cachet(s) par repas :", min_value=1, value=default_nb_cachet, key="side_nb_cachets_repas")

    if st.sidebar.button("💾 Enregistrer le médicament", key="side_save_med_btn"):
        if med_name:
            if current_med_name in meds: del meds[current_med_name]
            meds[med_name] = {
                "stock": int(stock_actuel), "timing": timing, "start_date": str(date.today()), "is_evolution": False, "phases": [{"dose": nb_cachets_repas, "duration": 9999}],
                "prend_matin": p_matin, "prend_midi": p_midi, "prend_soir": p_soir, "nb_cachet_par_repas": int(nb_cachets_repas)
            }
            save_json(meds, MEDS_FILE)
            st.sidebar.success("🎉 C'est bien enregistré !")
            redemarrer()

if meds:
    with st.sidebar.expander("🗑️ Supprimer un Médicament", expanded=False):
        med_to_delete = st.sidebar.selectbox("Choisir à supprimer", list(meds.keys()), key="side_del_med_select")
        if st.sidebar.button("🚨 Confirmer la suppression", key="side_del_med_btn"):
            del meds[med_to_delete]
            save_json(meds, MEDS_FILE)
            st.sidebar.success("🚨 Médicament supprimé !")
            redemarrer()

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
            st.caption(f"Moments requis : {'🌅 Matin ' if info.get('prend_matin') else ''}{'☀️ Midi ' if info.get('prend_midi') else ''}{'🌙 Soir' if info.get('prend_soir') else ''} — Prendre **{info.get('nb_cachet_par_repas', 1)} cachet(s)** ({info.get('timing')})")
            col_m, col_mid, col_s = st.columns(3)
            matin_check, midi_check, soir_check = False, False, False
            
            with col_m:
                if info.get("prend_matin", True): 
                    matin_check = st.checkbox("🌅 Pris le Matin", key=f"t1_{name}_matin_unique_key_securisee")
            with col_mid:
                if info.get("prend_midi", False): 
                    midi_check = st.checkbox("☀️ Pris le Midi", key=f"t1_{name}_midi_unique_key_securisee")
            with col_s:
                if info.get("prend_soir", True): 
                    soir_check = st.checkbox("🌙 Pris le Soir", key=f"t1_{name}_soir_unique_key_securisee")
                    
            prises_details[name] = {"Matin": matin_check, "Midi": midi_check, "Soir": soir_check, "dose_unitaire": info.get("nb_cachet_par_repas", 1)}
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
        liste_symp_cycle = ["Coup de barre (Après repas)", "Envie de sucre subite", "Maux de tête / Migraine", "Crampes pelviennes / Ovaires", "Poussée d'acné", "Sauts d'humeur / Irritabilité", "Seins douloureux", "Rétention d'eau"]
        c_c1, c_c2 = st.columns(2)
        for idx, s in enumerate(liste_symp_cycle):
            with c_c1 if idx % 2 == 0 else c_c2:
                if st.checkbox(s, key=f"t1_cycle_symptome_{s}_unique_key"): symp_cycle_choisis.append(s)
                
        note_jour = st.text_input("Notes libres sur ta journée", placeholder="RAS", key="t1_note_libre_validation_unique")
        
        if st.button("✅ Enregistrer ma journée", key="t1_submit_bouton_validation_final_unique"):
            new_entries = []
            for name, moments in prises_details.items():
                moments_cochés = [k for k, v in moments.items() if k in ["Matin", "Midi", "Soir"] and v]
                if len(moments_cochés) > 0:
                    total_de_cachets_pris = len(moments_cochés) * moments["dose_unitaire"]
                    meds[name]["stock"] = max(0, meds[name]["stock"] - total_de_cachets_pris)
                    txt_prise = ", ".join(moments_cochés) + f" ({total_de_cachets_pris} cachet(s) au total)"
                else:
                    txt_prise = "Aucune"
                new_entries.append({
                    "Date": str(date.today()), "Médicament": name, "Prise": txt_prise, "Moment Repas": meds[name]["timing"], 
                    "Symptômes Traitement": ", ".join(symp_med_choisis) if symp_med_choisis else "Aucun",
                    "Symptômes SOPK/Pré-Diabète": ", ".join(symp_cycle_choisis) if symp_cycle_choisis else "Aucun", "Note": note_jour
                })
            save_json(meds, MEDS_FILE)
            history_df = pd.concat([history_df, pd.DataFrame(new_entries)], ignore_index=True)
            save_df(history_df, HISTORY_FILE)
            st.success("🎉 C'est bien enregistré dans ton historique !")
            redemarrer()
        # --- ENRICHISSEMENT ANNONCES ET DOSSIER DU BÉBÉ ---
        st.write("### 👶 Informations Secrètes sur Bébé(s)")
        poids_config["genre_bebe"] = st.selectbox("👶 Genre du bébé :", ["Non renseigné / Surprise 🤫", "Fille 🌸", "Garçon 💎", "Jumeaux / Grossesse Multiple 🤰🤰"], index=["Non renseigné / Surprise 🤫", "Fille 🌸", "Garçon 💎", "Jumeaux / Grossesse Multiple 🤰🤰"].index(poids_config.get("genre_bebe", "Non renseigné / Surprise 🤫")), key="t2_genre_bebe_sel")
        poids_config["notes_bebe"] = st.text_input("📝 Notes sur les Échographies (ex: Il bouge beaucoup, poids estimé...)", value=poids_config.get("notes_bebe", ""), key="t2_notes_bebe_txt")
        
        if st.button("💾 Sauvegarder les informations du Bébé", key="btn_save_info_bebe_final"):
            save_json(poids_config, "config_grossesse.json")
            st.success("🎉 Informations obstétricales enregistrées avec succès !")
            redemarrer()
# --- TAB 3 : RDV MEDICAUX ---
with tab3:
    st.subheader("📅 Gestion de tes Rendez-vous Médicaux")
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1: rdv_date = st.date_input("Date du RDV", value=date.today(), key="t3_date")
    with col_r2: rdv_time = st.text_input("Heure", placeholder="14:30", key="t3_time")
    with col_r3: rdv_doc = st.text_input("Médecin / Spécialité", placeholder="Gynécologue", key="t3_doc")
    rdv_place = st.text_input("🏢 Lieu / Adresse du RDV", placeholder="Cabinet privé, Clinique, Hôpital...", key="t3_place")
    rdv_note = st.text_input("Motif ou notes (ex: Échographie)", key="t3_note")
    if st.button("📌 Ajouter ce rendez-vous", key="t3_submit_direct"):
        new_rdv = pd.DataFrame([{"Date": str(rdv_date), "Heure": rdv_time, "Médecin / Spécialité": rdv_doc, "Lieu": rdv_place, "Notes": rdv_note}])
        rdv_df = pd.concat([rdv_df, new_rdv], ignore_index=True).sort_values(by="Date").reset_index(drop=True)
        save_df(rdv_df, RDV_FILE)
        st.success("🎉 Rendez-vous ajouté avec succès !")
        redemarrer()
    if not rdv_df.empty: st.dataframe(rdv_df, use_container_width=True)
# --- TAB 4 : SUIVI GLYCÉMIE & NUTRITION ---
with tab4:
    st.subheader("🥗 Mon Suivi & Objectifs Pré-Diabète")
    st.info("💪 **Chaque petit pas compte !** Ton corps a besoin de bienveillance. La Metformine travaille main dans la main avec tes repas triés.")
    st.write("---")
    
    def sauvegarder_metabolique(date_cible, colonne_nom, valeur_texte, conseil_texte=""):
        global glyc_df_local
        d_str = str(date_cible)
        if glyc_df_local.empty or d_str not in glyc_df_local["Date"].values:
            nouvelle_ligne = {col: "Non renseigné" for col in glyc_df_local.columns}
            nouvelle_ligne["Date"] = d_str
            nouvelle_ligne["Glycémie à jeun"], nouvelle_ligne["Glycémie Post-Prandiale"] = "-", "-"
            glyc_df_local = pd.concat([glyc_df_local, pd.DataFrame([nouvelle_ligne])], ignore_index=True)
            
        masque = glyc_df_local["Date"] == d_str
        glyc_df_local.loc[masque, colonne_nom] = str(valeur_texte)
        if conseil_texte:
            ancien = str(glyc_df_local.loc[masque, "Conseils & Alertes"].values)
            glyc_df_local.loc[masque, "Conseils & Alertes"] = conseil_texte if ('Non renseigné' in ancien or '-' in ancien) else ancien + " | " + conseil_texte
        save_df(glyc_df_local, GLYC_FILE)

    st.write("### 📝 1. Enregistrer une Glycémie Unitaire")
    glyc_g_date = st.date_input("🗓️ Date", value=date.today(), key="t4_g_date")
    glyc_mode = st.selectbox("Moment", ["Matin à jeun", "2h après le repas"], key="t4_g_moment")
    glyc_val = st.number_input("Sucre (g/L)", min_value=0.0, max_value=3.0, value=0.95, step=0.01, key="t4_g_val")
    if st.button("💾 Sauvegarder cette valeur uniquement", key="t4_submit_glyc_only"):
        sauvegarder_metabolique(glyc_g_date, "Glycémie à jeun" if glyc_mode == "Matin à jeun" else "Glycémie Post-Prandiale", f"{glyc_val} g/L", f"{glyc_mode}: {glyc_val} g/L")
        st.success("🎉 Enregistré !")
        redemarrer()
        
    st.write("---")
    st.write("### 🚶‍♀️ 2. Valider mon activité physique")
    pas_date = st.date_input("🗓️ Date", value=date.today(), key="t4_p_date")
    pas_moment = st.selectbox("Moment", ["Après le Petit-Déjeuner", "Après le Déjeuner", "Après le Dîner"], key="t4_p_moment")
    nb_pas = st.number_input("Pas :", min_value=0, value=1500, step=100, key="t4_p_val")
    if st.button("💾 Sauvegarder mes pas", key="t4_submit_pas"):
        sauvegarder_metabolique(pas_date, "Activité Physique", f"{nb_pas} pas ({pas_moment})", f"Marche: {nb_pas}")
        st.success("🏃‍♀️ Enregistré !")
        redemarrer()

    st.write("---")
    st.write("### 🥗 3. Valider mes repas du jour")
    rep_date = st.date_input("🗓️ Date repas", value=date.today(), key="t4_r_date_indep")
    leg_choix = st.checkbox("🥗 Fibres / Légumes en premier", key="t4_r_leg_indep")
    met_choix = st.checkbox("🍋 Metformine prise", key="t4_r_met_indep")
    txt_h = f"{'Légumes 1er' if leg_choix else 'Glucides'} + {'Metformine' if met_choix else 'Sans'}"
    
    c_r1, c_r2, c_r3, c_r4, c_r5 = st.columns(5)
    with c_r1:
        if st.button("🍳 P'tit Déj Salé"): sauvegarder_metabolique(rep_date, "Petit-Déjeuner", txt_h, "Déj Salé."); st.success("Enregistré !"); redemarrer()
        if st.button("❌ Saut Déj"): sauvegarder_metabolique(rep_date, "Petit-Déjeuner", "Sauté", "Saut Déj."); st.error("Enregistré !"); redemarrer()
    with c_r2:
        if st.button("💾 Déjeuner"): sauvegarder_metabolique(rep_date, "Déjeuner", txt_h, "Déjeuner."); st.success("Enregistré !"); redemarrer()
    with c_r3:
        if st.button("💾 Dîner"): sauvegarder_metabolique(rep_date, "Dîner", txt_h, "Dîner."); st.success("Enregistré !"); redemarrer()
    with c_r4:
        if st.button("💾 Dessert"): sauvegarder_metabolique(rep_date, "Dessert / Plaisir", txt_h, "Dessert."); st.success("Enregistré !"); redemarrer()
    with c_r5:
        if st.button("💾 Grignotage"): sauvegarder_metabolique(rep_date, "Grignotage / Encas", txt_h, "Grignotage."); st.info("Enregistré !"); redemarrer()

    st.write("---")
    st.write("### 🥤 4. Valider mes boissons du jour")
    boiss_date = st.date_input("🗓️ Date boisson", value=date.today(), key="t4_b_date")
    v_eau = st.number_input("💧 Eau (verres)", min_value=0, value=4, key="t4_b_eau")
    v_sirop = st.number_input("🥤 Sirop (verres)", min_value=0, value=0, key="t4_b_sirop")
    v_sucre = st.number_input("🥤 Sodas (verres)", min_value=0, value=0, key="t4_b_sucre")
    v_nature = st.number_input("☕ Infusions (verres)", min_value=0, value=1, key="t4_b_sans_sucre")
    if st.button("💾 Sauvegarder boissons", key="t4_submit_boiss_det"):
        sauvegarder_metabolique(boiss_date, "Hydratation (Verres)", f"Eau:{v_eau}|Sirop:{v_sirop}|Sodas:{v_sucre}|Thé:{v_nature}", "Hydratation ok")
        st.success("🥤 Enregistré !"); redemarrer()

    st.write("---")
    st.write("### ⚖️ 5. Mon Suivi de Poids Hebdomadaire & IMC")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1: poids_date = st.date_input("🗓️ Date de la pesée", value=date.today(), key="t4_poids_date")
    with col_p2: poids_val = st.number_input("Ton poids actuel (kg)", min_value=30.0, max_value=200.0, value=70.0, step=0.1, key="t4_poids_val")
    with col_p3: taille_cm = st.number_input("Ta taille (en cm)", min_value=100, max_value=250, value=165, step=1, key="t4_taille_val")
    poids_note = st.text_input("Note sur la pesée", key="t4_poids_note")
    
    if st.button("💾 Sauvegarder ma pesée hebdomadaire", key="t4_submit_poids"):
        if not poids_df_local.empty: poids_df_local = poids_df_local[poids_df_local["Date"] != str(poids_date)]
        new_poids = pd.DataFrame([{"Date": str(poids_date), "Poids (kg)": poids_val, "Note": poids_note, "Taille (cm)": taille_cm}])
        poids_df_local = pd.concat([poids_df_local, new_poids], ignore_index=True).sort_values(by="Date").reset_index(drop=True)
        save_df(poids_df_local, POIDS_FILE)
        st.success("🎉 Pesée enregistrée avec succès sur ta fiche !")
        redemarrer()
        
    if not poids_df_local.empty:
        taille_m = taille_cm / 100.0
        imc = round(poids_val / (taille_m * taille_m), 1)
        st.write(f"#### 📢 Analyse de ton IMC en temps réel :")
        st.markdown(f"🔹 Votre **IMC actuel est de {imc}**.")
        if imc < 18.5: st.warning("⚠️ **Interprétation : Insuffisance pondérale.**")
        elif 18.5 <= imc <= 24.9: st.success("🟢 **Interprétation : Corpulence normale (Poids santé).**")
        elif 25.0 <= imc <= 29.9: st.info("🟡 **Interprétation : Surpoids.**")
        else: st.error("🔴 **Interprétation : Obésité.**")

        if len(poids_df_local) >= 2:
            poids_df_local = poids_df_local.sort_values(by="Date").reset_index(drop=True)
            dernier_p = poids_df_local["Poids (kg)"].iloc[-1]
            avant_dernier_p = poids_df_local["Poids (kg)"].iloc[-2]
            diff = round(dernier_p - avant_dernier_p, 1)
            st.write(f"#### 🔄 Écart de poids en direct :")
            if diff < 0: st.success(f"📉 **Félicitations !** Tu as perdu **{-diff} kg** since ta pesée précédente !")
            elif diff > 0: st.warning(f"📈 **Note :** Tu as pris **+{diff} kg**.")
            else: st.info("⚖️ **Stabilité parfaite !**")

        st.write("#### 📈 Ta Courbe d'Évolution du Poids")
        import altair as alt
        graphique_poids = alt.Chart(poids_df_local.copy()).mark_line(point=True, color="#e377c2").encode(x=alt.X('Date:T', title='Date'), y=alt.Y('Poids (kg):Q', title='Masse (kg)', scale=alt.Scale(domain=[45.0, 120.0]))).properties(width=450, height=200)
        st.altair_chart(graphique_poids, use_container_width=False)
        
        st.write("#### 🕒 Historique et Correction de tes Pesées (Style Excel)")
        edited_poids_df = st.data_editor(poids_df_local, use_container_width=True, num_rows="dynamic", key="editor_poids_tab4_direct")
        if st.button("💾 Sauvegarder les corrections du Poids", key="btn_save_poids_tab4"):
            save_df(edited_poids_df, POIDS_FILE); st.success("🎉 Historique de poids mis à jour !"); redemarrer()

    st.write("---")
    st.write("### 📋 Les Règles d'or de ton alimentation (Rappels) :")
    st.markdown("""
    * **📉 Privilégie l'Index Glycémique (IG) Bas :** Remplace le pain blanc par sa version complète.
    * **🔄 L'ordre des aliments :** Commence toujours par les légumes, puis les protéines (viande, œufs), et finis par les féculents.
    """)
# --- TAB 5 : HISTORIQUE GENERAL & TABLEAUX EXCEL ---
with tab5:
    st.subheader("📜 Historique Général & Modifications en Direct")
    if meds:
        meds_df = pd.DataFrame.from_dict(meds, orient='index')
        if 'stock' in meds_df.columns:
            st.write("### 📦 1. État réel et modification de tes stocks :")
            meds_df['stock'] = meds_df['stock'].astype(int)
            edited_meds_df = st.data_editor(meds_df[['stock', 'timing']], use_container_width=True, key="editor_meds_stocks_final_repare")
            if st.button("💾 Enregistrer les modifications de Stock", key="btn_save_edited_meds_final_repare"):
                for m_idx in edited_meds_df.index:
                    meds[m_idx]['stock'] = int(edited_meds_df.loc[m_idx, 'stock'])
                    meds[m_idx]['timing'] = edited_meds_df.loc[m_idx, 'timing']
                save_json(meds, MEDS_FILE); st.success("🎉 Stocks mis à jour !"); redemarrer()
                
    st.write("---")
    st.write("### 🕒 2. Consultation et Modification de tes Journaux de bord :")
    
    st.write("**Journal Spécial Protocole PMA (Modifications en direct) :**")
    if not pma_df.empty:
        edited_pma_df = st.data_editor(pma_df, use_container_width=True, num_rows="dynamic", key="editor_pma_table_final_repare")
        if st.button("💾 Sauvegarder les modifications du Protocole PMA", key="btn_save_edited_pma_final"):
            save_df(edited_pma_df, PMA_FILE); st.success("🎉 Dossier de suivi PMA mis à jour !"); redemarrer()
    else: st.caption("Le journal de protocole PMA is vide pour le moment.")
    
    st.write("---")
    st.write("**Journal Unique Métabolique (Une ligne par jour) :**")
    if not glyc_df_local.empty:
        edited_glyc_df = st.data_editor(glyc_df_local, use_container_width=True, num_rows="dynamic", key="editor_glyc_table_final_repare")
        if st.button("💾 Sauvegarder les modifications de la Nutrition", key="btn_save_edited_glyc_final_repare"): save_df(edited_glyc_df, GLYC_FILE); st.success("🎉 Tableau de nutrition corrigé !"); redemarrer()
    st.write("---")
    st.write("**Journal des Prises de médicaments & Symptômes :**")
    if not history_df.empty:
        edited_history_df = st.data_editor(history_df, use_container_width=True, num_rows="dynamic", key="editor_history_table_final_repare")
        if st.button("💾 Sauvegarder les modifications des Prises", key="btn_save_edited_history_final_repare"): save_df(edited_history_df, HISTORY_FILE); st.success("🎉 Tableau des prises corrigé !"); redemarrer()
    st.write("---")
    st.write("**Journal du Suivi Féminin & Températures :**")
    if not cycle_df.empty:
        edited_cycle_df = st.data_editor(cycle_df, use_container_width=True, num_rows="dynamic", key="editor_cycle_table_final_repare")
        if st.button("💾 Sauvegarder les modifications du Cycle", key="btn_save_edited_cycle_final_repare"): save_df(edited_cycle_df, CYCLE_FILE); st.success("🎉 Tableau de cycle corrigé !"); redemarrer()
