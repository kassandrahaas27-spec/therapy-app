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
    st.rerun()

# --- SYSTÈME DE CHARGEMENT SÉCURISÉ ---
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

# Chargement sécurisé depuis Supabase
history_df = load_db_from_supabase("historique_prises", ["Date", "Médicament", "Prise", "Moment Repas", "Symptômes Traitement", "Symptômes SOPK/Pré-Diabète", "Note"])
cycle_df = load_db_from_supabase("cycle_temperature", ["Date", "Cycle Status", "Température", "Rapport Sexuel", "Note", "Mode Parcours"])
rdv_df = load_db_from_supabase("rdv_medicaux", ["Date", "Heure", "Médecin / Spécialité", "Lieu", "Notes"])
glyc_df_local = load_db_from_supabase("suivi_glycemie", ["Date", "Glycémie à jeun", "Glycémie Post-Prandiale"])
poids_df_local = load_db_from_supabase("suivi_poids", ["Date", "Poids (kg)", "Note", "Taille (cm)"])

# Chargement sécurisé des médicaments
meds = {}
try:
    meds_response = supabase.table("medicaments").select("*").execute()
    if meds_response.data:
        for row in meds_response.data:
            if isinstance(row, dict) and "name" in row and "config" in row:
                config_data = row["config"]
                meds[row["name"]] = json.loads(config_data) if isinstance(config_data, str) else config_data
except:
    meds = {}

# Chargement sécurisé configuration grossesse
poids_config = {}
try:
    config_response = supabase.table("config_grossesse").select("*").execute()
    if config_response.data:
        config_data = config_response.data["config"] if isinstance(config_response.data, list) else config_response.data.get("config", "{}")
        poids_config = json.loads(config_data) if isinstance(config_data, str) else config_data
except:
    poids_config = {}

# --- MENU DE GAUCHE ---
st.sidebar.header("⚙️ Configuration Globale")
parcours_mode = st.sidebar.selectbox("🌸 Ton parcours actuel :", ["Suivi de Cycle & Essai Bébé", "Suivi de Grossesse Évolutif", "Parcours PMA (Procréation Médicalement Assistée)"], key="side_parcours_mode")

with st.sidebar.expander("✏️ Ajouter ou Modifier un Médicament", expanded=True):
    med_mode = st.sidebar.radio("Action", ["Nouveau médicament", "Modifier un existant"], key="side_med_mode")
    current_med_name = ""
    default_stock = 30
    default_timing = "Début de repas"
    default_m, default_mi, default_s = True, False, True
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
        default_is_evo = info_m.get("is_evolution", False)

    med_name = st.sidebar.text_input("Nom du médicament (ex: Metformine)", value=current_med_name if med_mode == "Modifier un existant" else "", key="side_med_name").strip()
    stock_actuel = st.sidebar.number_input("Stock de comprimés", min_value=0, value=default_stock, key="side_med_stock")
    timing = st.sidebar.selectbox("Moment lié au repas", ["Début de repas", "Milieu de repas", "Fin de repas"], index=0, key="side_med_timing")
    
    st.sidebar.markdown("**Moments de prise :**")
    p_matin = st.sidebar.checkbox("🌅 Matin", value=default_m, key="side_p_matin")
    p_midi = st.sidebar.checkbox("☀️ Midi", value=default_mi, key="side_p_midi")
    p_soir = st.sidebar.checkbox("🌙 Soir", value=default_s, key="side_p_soir")
    
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
                "stock": int(stock_actuel), "timing": timing, "start_date": str(date_debut_traitement), "is_evolution": is_evolution, "phases": phases_save,                "prend_matin": p_matin, "prend_midi": p_midi, "prend_soir": p_soir, "nb_cachet_par_repas": int(nb_cachets_repas)
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
        liste_symp_cycle = ["Coup de barre (Après repas)", "Envie de sucre subite", "Maux de tête / Migraine", "Crampes pelviennes / Ovaires", "Poussée d'acné", "Sauts d'humeur / Irritabilité", "Seins douloureux", "Rétention d'eau"]
        for idx, s in enumerate(liste_symp_cycle):
            if st.checkbox(s, key=f"t1_cycle_symptome_{s}_unique_key"): symp_cycle_choisis.append(s)

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
                
                info_m["stock"] = max(0, int(info_m.get("stock", 30)) - total_de_cachets_pris)
                supabase.table("medicaments").upsert({"name": name, "config": json.dumps(info_m)}).execute()
                
            st.success("🎉 Enregistré dans ton cloud Supabase !")
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

            st.write("#### 📅 Mon Calendrier Prédictif du Cycle")
            regles_dates = cycle_df[cycle_df["Cycle Status"] == "🩸 Début des Règles"]["Date"].tolist()
            
            if regles_dates:
                dernieres_regles = datetime.strptime(regles_dates[-1], "%Y-%m-%d").date()
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
        if save_row_to_supabase("rdv_medicaux", row_r):
            st.success("🎉 Rendez-vous ajouté au Cloud !")
            redemarrer()
    if not rdv_df.empty:
        st.dataframe(rdv_df, use_container_width=True)
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
