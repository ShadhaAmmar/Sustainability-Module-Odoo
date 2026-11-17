# Durabilité & Empreinte Carbone — Odoo 17

Module testé sur Odoo 17.0 (installation + tests fonctionnels + rendu PDF).

## Installation
1. Copier le dossier `carbon_footprint_management` dans un dossier listé dans `addons_path`.
2. Installer :  `./odoo-bin -c <conf> -d <base> -i carbon_footprint_management --stop-after-init`
3. Relancer le serveur. Menu : **Durabilité & Carbone**.
4. Réglages > Utilisateurs : ajouter les utilisateurs au groupe **Durabilité & Carbone / Utilisateur**
   (ou **Responsable durabilité** pour valider et certifier).

## À configurer avant usage réel
* Menu Configuration > Facteurs d'émission : remplacer les valeurs INDICATIVES par vos sources officielles
  (ADEME Base Empreinte, DEFRA, facteur réseau électrique de votre pays).
* Renseigner l'intensité carbone des produits (onglet « Durabilité ») ou la calculer depuis la nomenclature.
