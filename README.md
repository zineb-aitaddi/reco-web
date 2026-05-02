# Reconnaissance Faciale avec Firebase

## Description

Ce projet est une application web de reconnaissance faciale qui permet d'uploader des images depuis une interface web, de les stocker dans Firebase Storage, puis d'enregistrer leurs informations dans Firestore.

Les images envoyées peuvent ensuite être traitées avec un script Python afin d'effectuer une comparaison avec des visages connus et afficher le résultat de reconnaissance.

---

## Objectif du projet

L'objectif de ce projet est de mettre en place un système simple de reconnaissance faciale basé sur :

- Une interface web pour uploader des photos
- Le stockage des images dans Firebase Storage
- L'enregistrement des liens des images dans Firestore
- Un traitement Python pour analyser les images
- Une base locale de visages connus

Ce projet a été réalisé dans un cadre académique afin de pratiquer l'intégration entre le développement web, Firebase et le traitement d'images avec Python.

---

## Fonctionnalités

- Upload d'image depuis le navigateur
- Prise de photo depuis un téléphone ou un ordinateur
- Stockage automatique dans Firebase Storage
- Enregistrement de l'URL de l'image dans Firestore
- Authentification anonyme Firebase
- Traitement des images avec Python
- Comparaison avec des visages connus
- Organisation sécurisée des fichiers sensibles

---

## Technologies utilisées

- HTML
- CSS
- JavaScript
- Firebase Storage
- Firebase Firestore
- Firebase Authentication
- Python
- Git / GitHub

---

## Structure du projet

```text
reco-web/
│
├── public/
│   └── index.html
│
├── process_and_display.py
├── firebase.json
├── .firebaserc
├── .gitignore
└── README.md
```

---

## Fichiers privés non inclus

Pour des raisons de sécurité et de confidentialité, certains fichiers ne sont pas inclus dans ce dépôt GitHub :

```text
serviceAccountKey.json
known_faces/
raw_images/
uploads/
```

Ces fichiers contiennent des informations sensibles comme les clés Firebase Admin ou les images utilisées pour la reconnaissance faciale.

---

## Installation et utilisation

### 1. Cloner le projet

```bash
git clone https://github.com/Zineb-aitaddi/reco-web.git
```

### 2. Entrer dans le dossier du projet

```bash
cd reco-web
```

### 3. Configurer Firebase

Le projet utilise Firebase pour :

- Storage
- Firestore
- Authentication

Il faut créer un projet Firebase, activer les services nécessaires, puis configurer les règles de sécurité selon les besoins du projet.

---

## Interface web

L'interface web se trouve dans :

```text
public/index.html
```

Elle permet à l'utilisateur de choisir ou prendre une photo, puis de l'envoyer vers Firebase.

---

## Script Python

Le fichier :

```text
process_and_display.py
```

permet de traiter les images uploadées et de réaliser la partie reconnaissance faciale.

---

## Sécurité

Ce projet utilise un fichier `.gitignore` pour éviter d'envoyer les fichiers sensibles sur GitHub.

Les clés privées, les images personnelles et les dossiers contenant les visages connus ne doivent jamais être publiés dans un dépôt public.

---

## Compétences mises en pratique

Ce projet m'a permis de pratiquer :

- L'intégration de Firebase dans une application web
- L'upload d'images vers Firebase Storage
- L'utilisation de Firestore pour stocker les données
- Le développement d'une interface web simple
- Le traitement d'images avec Python
- La structuration d'un projet GitHub
- La gestion des fichiers sensibles avec `.gitignore`

---

## Aperçu du projet

Interface d'upload des images vers Firebase :

```text
public/index.html
```


## Auteur

Projet réalisé par **Zineb Aitaddi**.

---

## Contact

- GitHub : [Zineb-aitaddi](https://github.com/Zineb-aitaddi)
