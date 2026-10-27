VS & VUSLKY — Site web local
============================

Démarrage rapide (Windows)
1. Installe Python 3.10 ou plus récent si nécessaire.
2. Extrais le ZIP dans un dossier.
3. Ouvre CMD dans le dossier Vs_Vuslky.
4. Exécute :
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
5. Visite : http://127.0.0.1:5000

Arrêt : Ctrl+C dans CMD.

Panel administrateur
- URL : http://127.0.0.1:5000/admin/login
- Identifiant initial : vsvulskytropuhq
- Mot de passe initial : Cavaettoimvi

IMPORTANT — sécurité
- Ces identifiants initiaux sont inscrits dans la documentation du paquet. Change-les avant toute utilisation réelle.
- Pour définir un nouvel utilisateur et mot de passe haché, crée un hash avec :
  python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('TON_NOUVEAU_MOT_DE_PASSE'))"
- Puis, dans CMD avant de lancer le site :
  set VSV_ADMIN_USER=ton_utilisateur
  set VSV_ADMIN_PASSWORD_HASH=COLLE_ICI_LE_HASH
  set VSV_SECRET_KEY=une-longue-cle-aleatoire
- Le site utilise un hash du mot de passe pour la vérification. Le mot de passe n'est pas affiché dans le formulaire.
- Le mode par défaut est local uniquement (127.0.0.1), ne le publie pas directement sur Internet sans déploiement et mesures de sécurité adaptés.

Importer des fichiers
- Connecte-toi au panel admin puis importe des fichiers CSV, JSON ou TXT (20 Mo maximum).
- Les fichiers sont placés dans DB/ et recherchés automatiquement.
- Les fichiers doivent contenir des données que tu es autorisé à traiter.
- Pour CSV, utilise une première ligne avec les noms de colonnes.
- La recherche accepte plusieurs critères combinés : prenom, nom, annee, ville, code_postal et reference (ou numero_dossier).
- Exemple : prenom,nom,annee,ville,code_postal,reference. Les noms de colonnes peuvent aussi être en français avec accents ou en anglais (first_name, last_name, year, city, postal_code, record_id).
- Pour JSON, utilise une liste d'objets ou un objet contenant une clé "records".
- Seuls les champs non sensibles prévus par le formulaire sont recherchés et affichés : prénom, nom, année, ville, code postal et référence de dossier. Les e-mails, téléphones, adresses détaillées, dates de naissance complètes, mots de passe et tokens ne sont pas recherchés ni affichés.

Demandes de retrait
- La page « Se retirer » enregistre une demande dans la base locale.
- Un administrateur doit vérifier la demande et modifier les fichiers sources manuellement. Changer le statut ne supprime pas automatiquement les données.

Limites
- Version de démonstration locale, sans HTTPS, sans protection CSRF dédiée ni système multi-utilisateur. Le design est adapté aux écrans mobiles et ordinateur.
- Ne pas exposer ce serveur sur un réseau public. Pour une mise en production, ajouter CSRF, limitation de tentatives, stockage de secrets hors code, HTTPS, sauvegardes et procédure de suppression vérifiable.
