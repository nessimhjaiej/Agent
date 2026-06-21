# Plan Des Sprints Pour Le Rapport PFE

Ce document propose une base de redaction plus naturelle et plus proche d'un vrai chapitre de memoire pour le projet `Synapse`.  
L'idee est de transformer chaque sprint en chapitre LaTeX, avec une progression logique entre l'etude, les choix, la conception, la realisation et la retrospective.

Hypotheses retenues :

- duree d'un sprint : `3 semaines`
- date de depart du projet : `26/02/2026`
- decoupage base sur l'historique Git du depot `nessimhjaiej/Agent`
- presence d'un sprint precedent non detaille ici, ce qui decale la numerotation de `+1`

Decoupage adopte dans le rapport :

1. `Sprint 2 : 26/02/2026 -> 18/03/2026`
2. `Sprint 3 : 19/03/2026 -> 08/04/2026`
3. `Sprint 4 : 09/04/2026 -> 29/04/2026`

## Proposition De Structure LaTeX Par Sprint

Le modele suivant peut etre reutilise pour chaque chapitre :

1. Introduction
2. Backlog du sprint
3. Etude du besoin et etude technique
4. Choix technologiques
5. Conception de l'architecture
6. Realisation et mise en place
7. Fonctionnalites developpees
8. Retrospective du sprint

---

# Chapitre 4

## Etude Et Realisation Sprint 2 : Mise En Place Du Socle Technique Et De La Premiere Version Fonctionnelle

### 4.1 Introduction

Le sprint 2 correspond a la vraie phase de fondation technique de `Synapse`. Durant cette periode, l'objectif n'etait pas encore d'affiner l'experience utilisateur ou d'introduire des mecanismes d'orchestration avances, mais plutot de construire une base fiable sur laquelle les evolutions futures pourraient reposer. L'equipe s'est donc concentree sur la structuration du depot, la definition d'une architecture microservices, l'installation des premiers services backend et la mise en place d'un premier cycle complet allant de l'authentification jusqu'a la generation de reponse.

Ce sprint a egalement joue un role important dans la clarification de la vision du projet. A ce stade, il fallait valider que `Synapse` etait capable de gerer des documents, d'extraire leur contenu, d'indexer les passages utiles, puis de produire une reponse contextualisee a partir d'une question utilisateur. En d'autres termes, ce sprint a permis de passer d'une idee d'architecture a une premiere version executable du systeme.

### 4.2 Backlog Du Sprint 2

Les principales taches de ce sprint peuvent etre presentees comme suit :

- initialisation de l'arborescence du projet
- mise en place de la documentation technique et des README
- definition de l'architecture microservices
- mise en place du service d'authentification
- mise en place du service de preprocessing
- mise en place du service d'embedding
- mise en place du service de retrieval
- mise en place du service de generation
- mise en place du service d'ingestion
- integration Docker et Docker Compose
- connexion du frontend au backend
- integration initiale de l'espace admin et user
- ajout des premiers tests unitaires et d'integration
- premiers essais d'evaluation de la qualite des reponses

### 4.3 Etude Technique Du Sprint 2

#### 4.3.1 Etude De L'Architecture Microservices

Le choix d'une architecture microservices repondait a un besoin de modularite et de separation claire des responsabilites. Chaque service prend en charge une etape bien precise du cycle de traitement : authentification, ingestion, pretraitement, embeddings, recherche ou generation. Cette approche facilite la maintenance, permet de faire evoluer un composant sans remettre en cause l'ensemble du systeme, et rend l'architecture plus lisible dans un contexte de projet de fin d'etudes.

#### 4.3.2 Etude Du Flux Documentaire Initial

Le flux documentaire initial commence par le depot d'un document, suivi de son stockage et de l'enregistrement de ses metadonnees. Le contenu textuel est ensuite prepare par un service de preprocessing, segmente en passages exploitables, puis envoye au service d'embedding afin de produire les representations vectorielles necessaires a la recherche. Cette chaine est essentielle, car elle conditionne directement la qualite de la recherche et donc la pertinence des reponses generees.

#### 4.3.3 Etude Du Flux Question-Reponse

Le flux question-reponse repose sur une logique RAG classique. Lorsqu'un utilisateur pose une question, le systeme interroge d'abord la base vectorielle afin de recuperer les passages les plus pertinents. Ces passages sont ensuite injectes dans le contexte de generation, ce qui permet au modele de produire une reponse plus fiable, plus ciblee et mieux fondee sur le contenu documentaire reel.

#### 4.3.4 Etude De L'Authentification Et De La Gestion Des Roles

Des le debut du projet, il etait necessaire de distinguer les espaces d'usage entre les utilisateurs classiques et l'administrateur. L'etude a donc porte sur la gestion des sessions, la protection des routes et l'association entre l'identite authentifiee et les droits disponibles dans l'application. Cette base etait indispensable pour preparer les evolutions des sprints suivants.

### 4.4 Choix Technologiques Du Sprint 2

#### 4.4.1 Choix Du Framework Backend

Le backend s'appuie sur `FastAPI`, un framework bien adapte a la creation de services web modernes. Ce choix se justifie par sa simplicite de prise en main, son support naturel des API REST, sa documentation automatique et ses bonnes performances pour des services decoupes en plusieurs composants.

#### 4.4.2 Choix De La Technologie Frontend

Le frontend repose sur `React + Vite`, ce qui permet d'obtenir une interface rapide, reactive et facile a faire evoluer. Ce choix etait pertinent pour separer clairement la couche presentation de la couche metier tout en gardant une bonne fluidite de developpement.

#### 4.4.3 Choix Du Systeme D'Authentification

L'utilisation de `Supabase` a permis de gerer rapidement l'authentification, les sessions et une partie des metadonnees associees aux utilisateurs. Cela a evite de reimplementer un mecanisme complet d'authentification et a offert une base solide pour la gestion des acces.

#### 4.4.4 Choix Du Stockage Vectoriel Et Des Modeles

Pour la partie recherche semantique, la base vectorielle choisie est `Weaviate`. Ce choix s'inscrit dans une logique de recherche efficace sur les passages documents. Cote generation et embeddings, le projet prepare deja la coexistence entre plusieurs modeles ou fournisseurs, ce qui ouvre la voie a des ajustements ulterieurs selon les besoins du systeme.

### 4.5 Conception De L'Architecture Du Sprint 2

#### 4.5.1 Objectifs De L'Architecture Initiale

Les objectifs de l'architecture mise en place durant ce sprint etaient les suivants :

- garantir une bonne separation des responsabilites
- obtenir une base technique modulable
- rendre possible une integration progressive des services
- preparer le terrain pour les optimisations futures

#### 4.5.2 Architecture Generale Sprint 2

Emplacement suggere dans le memoire :

- `[Figure 4.1 : Architecture generale du sprint 2]`
- `[Capture / schema global du fonctionnement technique]`

#### 4.5.3 Diagramme Use Case Du Sprint 2

Emplacement suggere dans le memoire :

- `[Figure 4.2 : Diagramme de cas d'utilisation du sprint 2]`
- `[Schema des interactions entre admin, user et plateforme]`

#### 4.5.4 Diagrammes De Sequence Du Sprint 2

Les diagrammes de sequence permettent d'illustrer les premiers flux essentiels du systeme.

Emplacements suggeres dans le memoire :

- `[Figure 4.3 : Sequence d'authentification]`
- `[Figure 4.4 : Sequence d'ingestion et d'indexation documentaire]`
- `[Figure 4.5 : Sequence question - recherche - generation de reponse]`
- `[Capture d'ecran de l'interface de connexion]`
- `[Capture d'ecran de l'interface de depot de document]`
- `[Capture d'ecran de la premiere reponse generee avec sources]`

### 4.6 Mise En Place Des Composants Du Sprint 2

#### 4.6.1 Service D'Authentification

Le service d'authentification a permis de structurer les premieres regles d'acces au systeme. Il assure la connexion des utilisateurs, la gestion des sessions et la distinction entre les parcours admin et user.

#### 4.6.2 Service De Preprocessing

Le service de preprocessing prepare les documents avant leur indexation. Son role est de nettoyer, normaliser et segmenter le texte de maniere a produire des passages exploitables par les etapes ulterieures.

#### 4.6.3 Service D'Embedding

Le service d'embedding transforme les segments textuels en vecteurs numeriques. Cette etape est fondamentale, car elle rend possible la recherche semantique dans la base vectorielle.

#### 4.6.4 Service De Retrieval

Le service de retrieval interroge la base vectorielle afin de recuperer les passages les plus pertinents en fonction d'une question donnee. Il constitue le lien entre la connaissance indexee et la generation finale.

#### 4.6.5 Service De Generation

Le service de generation construit le contexte et formule la reponse finale. Il exploite les passages recuperes pour guider le modele et produire une sortie plus precise qu'une generation sans contexte.

#### 4.6.6 Service D'Ingestion

Le service d'ingestion coordonne le cycle documentaire : reception du fichier, declenchement du pretraitement, calcul des embeddings et mise a jour de l'etat du document dans le systeme.

#### 4.6.7 Frontend Et Integration Initiale

Le frontend a servi de point d'entree unique pour les utilisateurs et l'administrateur. Durant ce sprint, l'effort a surtout porte sur l'integration des premiers appels backend et sur la validation d'un parcours fonctionnel complet.

### 4.7 Fonctionnalites Developpees Dans Le Sprint 2

#### 4.7.1 Authentification Et Gestion Des Utilisateurs

Une premiere gestion des comptes utilisateurs a ete mise en place afin de controler l'acces a la plateforme. Cette fonctionnalite couvre la connexion, la persistance minimale des sessions et la distinction entre les droits d'un utilisateur classique et ceux d'un administrateur.

#### 4.7.2 Upload Et Indexation Des Documents

Le systeme est devenu capable de recevoir des documents, de les enregistrer, de les preparer puis de les indexer. Cette fonctionnalite constitue une brique centrale, car elle alimente directement la base de connaissances exploitee ensuite par le systeme RAG.

#### 4.7.3 Recherche Et Generation De Reponses

La recherche documentaire et la generation de reponses ont ete reliees dans un premier pipeline fonctionnel. L'utilisateur peut ainsi poser une question, obtenir une reponse contextualisee et beneficier d'un systeme fonde sur des passages reels extraits des documents.

#### 4.7.4 Tableau De Bord Initial Admin / User

Les premiers espaces d'interaction ont ete rendus operationnels, aussi bien pour l'utilisateur final que pour l'administrateur. Meme si l'interface restait encore simple, elle permettait deja de tester les parcours essentiels du projet.

#### 4.7.5 Mise En Place Des Tests Et De L'Environnement Docker

Afin de rendre le projet plus reproductible, un environnement conteneurise a ete introduit avec Docker Compose. Des premiers tests ont egalement ete ajoutes pour verifier le bon fonctionnement des services et reduire les risques de regression.

### 4.8 Retrospective Du Sprint 2

Le sprint 2 a permis de transformer une idee architecturale en une premiere plateforme executable. Il a confirme la pertinence du decoupage microservices et a valide le fonctionnement general du pipeline RAG. En revanche, cette premiere version a aussi mis en lumiere plusieurs besoins de consolidation, notamment autour de la stabilite des sessions, de la lisibilite des donnees documentaires et de la supervision administrative. Ces constats ont naturellement oriente le travail du sprint suivant.

Elements visuels utiles a inserer en fin de chapitre :

- `[Tableau de synthese du backlog realise]`
- `[Capture d'ecran du tableau de bord initial]`
- `[Photo ou figure de l'environnement d'execution local / Docker]`
- `[Encadre de conclusion du sprint]`

---

# Chapitre 5

## Etude Et Realisation Sprint 3 : Stabilisation Du Systeme, Tracabilite Documentaire Et Amelioration De L'Architecture

### 5.1 Introduction

Apres la mise en place du socle technique, le sprint 3 avait pour ambition de rendre `Synapse` plus stable, plus fiable et plus agreable a utiliser. L'objectif n'etait plus seulement de prouver que le systeme fonctionnait, mais de commencer a le rendre robuste dans un contexte d'usage plus realiste. L'accent a donc ete mis sur la persistance des sessions, la consultation des documents cote administration et la qualite des citations et apercus affiches a l'utilisateur.

### 5.2 Backlog Du Sprint 3

Les principales taches de ce sprint peuvent etre presentees comme suit :

- correction des problemes de deconnexion transitoire
- synchronisation de l'etat d'authentification entre onglets
- amelioration de la persistance des sessions
- enrichissement de la consultation admin des documents
- ajout des informations sur l'uploader
- alignement des citations avec les identifiants Supabase
- amelioration du chargement des apercus de sources
- securisation du flux d'ingestion
- evolution de l'interface voix vers texte
- ajustements de l'infrastructure et de la documentation

### 5.3 Etude Approfondie Du Systeme Au Sprint 3

#### 5.3.1 Etude De La Persistance Des Sessions

La persistance des sessions est devenue un enjeu important a partir du moment ou l'application a commence a etre testee dans des cas d'usage plus proches du reel. Il ne suffisait plus de permettre la connexion ; il fallait aussi eviter les deconnexions intempestives et garantir une experience continue pour l'utilisateur.

##### 5.3.1.1 Probleme Des Deconnexions Parasites

Les deconnexions transitoires observées durant les essais montraient que la gestion de l'etat de session devait etre consolidee. Cette sous-partie peut expliquer les causes detectees et les ajustements effectues pour reduire ces interruptions.

##### 5.3.1.2 Synchronisation Entre Plusieurs Onglets

Lorsque l'application est ouverte sur plusieurs onglets, l'etat d'authentification doit rester coherent. L'etude de ce point est importante, car elle touche a la fois a la securite, a la coherence fonctionnelle et au confort d'utilisation.

##### 5.3.1.3 Continuite De L'Experience Utilisateur

Au-dela de l'aspect purement technique, le maintien de la session participe a la qualite globale du produit. Une session stable renforce le sentiment de fiabilite et diminue la frustration de l'utilisateur.

#### 5.3.2 Etude De La Gestion Documentaire Admin

Le sprint 3 marque aussi une progression dans la visibilite des informations documentaires cote administration. L'objectif etait de fournir une lecture plus claire des documents deposes, de leur origine et de leur etat dans le systeme.

##### 5.3.2.1 Consultation De La Liste Des Documents

L'acces a une liste admin plus riche permet de mieux suivre les documents presents dans la plateforme et de verifier leur etat general.

##### 5.3.2.2 Association Des Metadonnees A L'Uploader

L'ajout d'informations sur l'uploader renforce la tracabilite des documents et facilite le suivi administratif.

##### 5.3.2.3 Gestion Des Statuts Et Des Informations Documentaires

Le fait d'associer les documents a des statuts et a des metadonnees exploitables contribue a une meilleure supervision du systeme.

#### 5.3.3 Etude De La Tracabilite Des Sources

Un systeme RAG credible doit permettre de justifier ses reponses. C'est pourquoi la tracabilite des sources a pris une place plus importante durant ce sprint.

##### 5.3.3.1 Alignement Des Citations Avec Les Identifiants

L'alignement entre citations affichees et identifiants documentaires est essentiel pour conserver une relation fiable entre reponse et source.

##### 5.3.3.2 Chargement Des Apercus Des Sources

L'aperçu de source permet de contextualiser les passages cites et aide l'utilisateur ou l'administrateur a verifier rapidement l'origine de l'information.

##### 5.3.3.3 Fiabilite De La Presentation Des Passages

Cette partie peut insister sur l'importance d'un affichage coherent, lisible et directement utile a la verification des reponses.

#### 5.3.4 Etude De La Securisation Du Flux D'Ingestion

La securisation du flux d'ingestion a consisté a mieux controler certains acces et certaines operations documentaires. Meme si cette phase reste encore intermediaire, elle prepare des evolutions plus marquees sur la securite dans le sprint suivant.

### 5.4 Choix Technologiques Et Evolutions Retenues

#### 5.4.1 Choix D'Approche Pour La Gestion De Session

Les evolutions retenues ont privilegie une logique de session plus stable et mieux synchronisee avec l'etat d'authentification, afin de reduire les effets de bord observes dans la premiere version.

#### 5.4.2 Evolution De L'Integration Supabase

L'integration avec `Supabase` a ete ajustee pour mieux gerer la persistance des sessions et exploiter plus proprement les metadonnees documentaires.

#### 5.4.3 Structuration Des Metadonnees Et Des Apercus

Une attention particuliere a ete accordee a la qualite des metadonnees, aux identifiants associes aux citations et a la recuperation des apercus afin de renforcer la tracabilite du systeme.

### 5.5 Conception De L'Architecture Du Sprint 3

#### 5.5.1 Objectifs De La Nouvelle Architecture

Les objectifs de cette evolution architecturale etaient les suivants :

- rendre les sessions plus stables
- enrichir la supervision admin
- ameliorer la tracabilite documentaire
- preparer le terrain pour une administration plus intelligente

#### 5.5.2 Architecture Generale Sprint 3

Emplacements suggeres dans le memoire :

- `[Figure 5.1 : Architecture generale du sprint 3]`
- `[Schema de stabilisation des sessions et de la tracabilite documentaire]`

#### 5.5.3 Diagramme Use Case Du Sprint 3

Emplacement suggere dans le memoire :

- `[Figure 5.2 : Diagramme de cas d'utilisation du sprint 3]`
- `[Schema des interactions admin et user autour des documents et sessions]`

#### 5.5.4 Diagramme De Consultation Admin Des Documents

Emplacements suggeres dans le memoire :

- `[Figure 5.3 : Sequence de consultation admin des documents]`
- `[Figure 5.4 : Schema de la gestion des citations et apercus]`
- `[Capture d'ecran de la liste des documents cote administration]`
- `[Capture d'ecran d'un apercu de source ou citation]`

### 5.6 Mise En Place Des Evolutions Du Sprint 3

#### 5.6.1 Gestion Des Sessions Et Authentification

Le travail a porte sur la correction des pertes de session, l'amelioration de la persistance et la propagation coherente de l'etat entre plusieurs contextes d'utilisation.

#### 5.6.2 Consultation Enrichie Des Documents

L'espace d'administration a ete enrichi afin d'offrir une vue plus detaillee sur les documents, leur origine et leurs informations associees.

#### 5.6.3 Gestion Des Citations Et Des Apercus

Les ajustements realises ont permis d'ameliorer la fiabilite des citations et le chargement des apercus de source, ce qui renforce la lisibilite globale du systeme.

#### 5.6.4 Securisation De L'Ingestion

Certaines verifications ont ete renforcees pour mieux encadrer les operations documentaires et rendre le flux plus robuste.

#### 5.6.5 Interface Voix Vers Texte

L'interface voix vers texte a connu des ajustements afin d'ameliorer l'experience d'interaction et de preparer de futurs usages plus fluides.

### 5.7 Fonctionnalites Developpees Dans Le Sprint 3

#### 5.7.1 Session Plus Robuste Et Plus Stable

Le systeme offre une meilleure continuite d'utilisation grace a une gestion de session plus fiable. Cette evolution ameliore directement la perception de qualite de l'application.

#### 5.7.2 Synchronisation D'Authentification Multi-Onglets

La synchronisation entre onglets permet de maintenir un comportement coherent de l'application, notamment lors des connexions, deconnexions et mises a jour d'etat.

#### 5.7.3 Consultation Admin Des Documents Enrichie

L'administrateur dispose d'une meilleure visibilite sur les documents presents dans la plateforme, avec des informations plus utiles pour le suivi et le controle.

#### 5.7.4 Tracabilite Amelioree Des Citations Et Sources

Les references aux documents sont plus cohérentes et plus faciles a verifier, ce qui contribue a la credibilite du systeme RAG.

#### 5.7.5 Securisation Progressive Des Flux Documentaires

Les ajustements de securisation realises durant ce sprint ne constituent pas encore une couche complete, mais ils posent des bases utiles pour des mecanismes de controle plus avances.

### 5.8 Retrospective Du Sprint 3

Le sprint 3 a transforme une premiere version fonctionnelle de `Synapse` en une version beaucoup plus stable et plus serieuse du point de vue de l'usage. La plateforme est devenue plus fiable sur la gestion des sessions, plus claire sur le plan documentaire et mieux preparee pour des evolutions d'administration avancee. Ce sprint a ainsi servi de pont entre la phase de fondation et la phase d'intelligence d'administration introduite ensuite.

Elements visuels utiles a inserer en fin de chapitre :

- `[Tableau comparatif avant / apres stabilisation]`
- `[Capture d'ecran montrant la consultation enrichie des documents]`
- `[Capture d'ecran illustrant la persistence de session ou la coherence multi-onglets]`
- `[Encadre de conclusion du sprint]`

---

# Chapitre 6

## Etude Et Realisation Sprint 4 : Administration Intelligente, Orchestration Agentique Et Optimisation Avancee

### 6.1 Introduction

Le sprint 4 marque une evolution majeure du projet. Alors que les deux sprints precedents ont permis de construire puis de stabiliser `Synapse`, cette nouvelle phase introduit une dimension plus intelligente et plus dynamique dans l'administration du systeme. L'objectif n'etait plus uniquement d'executer des flux documentaires ou d'afficher des informations, mais de permettre a l'espace admin de raisonner sur les demandes, de choisir une strategie d'action et de coordonner plusieurs outils ou services.

### 6.2 Backlog Du Sprint 4

Les principales taches de ce sprint peuvent etre resumees comme suit :

- integration de `LangGraph` dans `admin-service`
- mise en place d'une logique de classification des intentions
- ajout de branches d'execution : conseil, inspection, mutation, workflow
- detection des workflows multi-etapes
- exposition des strategies de chunking disponibles
- ajout ou evolution des endpoints de reranking
- ameliorations semantiques et optimisations multi-taches
- introduction du `security-service`
- correction du token admin bloquant certaines reponses
- ameliorations UI/UX du chat admin
- ameliorations responsive et animation de frappe

### 6.3 Etude Du Systeme Agentique Au Sprint 4

#### 6.3.1 Etude De L'Orchestration Basee Sur Graphe

Le recours a une orchestration basee sur graphe permet de structurer proprement la prise de decision de l'agent d'administration `Synapse`. Au lieu d'enchainer des appels de maniere rigide, le systeme peut classifier la demande, choisir une branche de traitement adaptee puis produire une synthese finale.

##### 6.3.1.1 Classification Des Intentions

La classification des intentions consiste a identifier la nature exacte de la demande admin : besoin d'information, inspection d'un etat, action de mutation ou lancement d'un workflow plus complexe.

##### 6.3.1.2 Branches D'Execution

Chaque branche du graphe repond a une logique differente. Cette organisation rend le systeme plus lisible, plus maintenable et plus facile a faire evoluer.

##### 6.3.1.3 Synthese Finale De La Reponse

La synthese finale joue un role central, car elle rassemble les resultats des branches traitees et les reformule dans une reponse claire pour l'administrateur.

#### 6.3.2 Etude Du Traitement Multi-Taches

Le traitement multi-taches repond au besoin de gerer des demandes qui ne se limitent pas a une seule action. Certaines questions admin supposent une sequence d'etapes, voire plusieurs verifications ou appels outils.

##### 6.3.2.1 Detection Des Demandes Multi-Etapes

Cette sous-partie peut expliquer comment le systeme reconnait qu'une demande doit etre decomposée en plusieurs operations.

##### 6.3.2.2 Coordination Entre Outils Et Services

Une fois la demande decomposée, le systeme doit coordonner les services existants de maniere coherente. C'est ici que l'orchestration agentique prend tout son sens.

##### 6.3.2.3 Optimisation Semantique

Les ameliorations semantiques visent a rendre les reponses plus pertinentes, les actions plus ciblees et l'exploitation des outils plus intelligente.

#### 6.3.3 Etude Du Volet Securite

Avec l'introduction d'un espace admin plus puissant, la question de la securite devient encore plus importante. Il ne s'agit plus seulement de proteger l'acces, mais aussi de controler les actions sensibles.

##### 6.3.3.1 Controle Des Appels Sensibles

Cette partie peut decrire les controles introduits avant certaines operations critiques.

##### 6.3.3.2 Separation Des Responsabilites

La separation des responsabilites permet de garder une architecture plus sure et plus lisible.

##### 6.3.3.3 Fiabilisation De L'Authentification Admin

La correction des problemes lies au token admin a contribue a rendre les reponses et les actions du chat admin plus fiables.

#### 6.3.4 Etude De L'Experience Admin

L'experience admin ne depend pas uniquement de la puissance du systeme, mais aussi de la maniere dont les reponses et les actions sont exposees dans l'interface.

##### 6.3.4.1 Evolution Du Chat D'Administration

Le chat admin devient un point central d'interaction, capable de guider l'utilisateur administrateur dans ses actions.

##### 6.3.4.2 Ameliorations Responsive

Les ameliorations responsive renforcent l'impression de finition et rendent l'interface plus confortable sur differents formats d'ecran.

##### 6.3.4.3 Rendu Des Reponses Et Feedback Visuel

Le soin apporte au rendu des reponses, aux messages et aux animations contribue a une experience plus fluide et plus professionnelle.

### 6.4 Choix Technologiques Et D'Architecture Du Sprint 4

#### 6.4.1 Choix De LangGraph Pour L'Orchestration

`LangGraph` a ete retenu pour modeliser le raisonnement de l'agent `Synapse` sous forme de graphe de traitement. Ce choix convient particulierement bien a des enchainements conditionnels et a des branches specialisees.

#### 6.4.2 Choix D'Une Architecture Admin Pilotee Par Intentions

L'approche par intentions permet d'eviter une logique trop rigide. Elle rend l'administration plus souple et plus adaptative face a des demandes variees.

#### 6.4.3 Choix D'Une Couche De Securite Dediee

L'introduction d'un `security-service` s'inscrit dans une logique de maturation de la plateforme, ou les controles de securite commencent a etre traites comme une preoccupation a part entiere.

### 6.5 Conception De L'Architecture Du Sprint 4

#### 6.5.1 Objectifs De L'Architecture Agentique

Les objectifs principaux de cette nouvelle architecture sont les suivants :

- centraliser l'administration intelligente
- mieux orchestrer les services existants
- introduire la multi-tache
- renforcer la securite
- ameliorer l'experience du chat admin

#### 6.5.2 Architecture Generale Sprint 4

Emplacements suggeres dans le memoire :

- `[Figure 6.1 : Architecture generale du sprint 4]`
- `[Schema de l'orchestration agentique du module d'administration]`
- `[Schema du traitement multi-taches et des controles de securite]`

#### 6.5.3 Diagramme Use Case Du Sprint 4

Emplacement suggere dans le memoire :

- `[Figure 6.2 : Diagramme de cas d'utilisation du sprint 4]`
- `[Schema des actions possibles dans le chat admin intelligent]`

### 6.6 Mise En Place Des Evolutions Du Sprint 4

#### 6.6.1 Integration De LangGraph Dans Admin-Service

L'integration de `LangGraph` a permis de structurer le comportement de l'agent admin et de sortir d'une logique purement lineaire.

#### 6.6.2 Detection D'Intentions Et Branches D'Execution

Le systeme peut desormais distinguer plusieurs types de demandes et choisir un traitement adapte.

#### 6.6.3 Gestion Des Workflows Multi-Etapes

Les workflows multi-etapes rendent possible la prise en charge de demandes plus riches, impliquant plusieurs actions successives ou coordonnees.

#### 6.6.4 Ajout Du Security-Service

L'ajout du `security-service` marque une etape importante dans la structuration des controles autour des operations sensibles.

#### 6.6.5 Evolution Des Endpoints Et Parametres RAG

Le sprint a aussi permis d'exposer davantage de parametres techniques, comme certaines strategies de chunking ou des endpoints lies au reranking.

#### 6.6.6 Ameliorations UI/UX Du Chat Admin

L'interface admin a beneficie de plusieurs refinements visuels et ergonomiques, donnant au systeme une impression de maturite plus forte.

### 6.7 Fonctionnalites Developpees Dans Le Sprint 4

#### 6.7.1 Chat Admin Intelligent

Le chat admin ne se contente plus d'afficher des informations ; il devient un veritable point d'orchestration des actions et des analyses.

#### 6.7.2 Inspection Et Pilotage Des Outils

L'administrateur peut interroger le systeme sur son etat, ses outils ou certaines configurations, ce qui renforce la capacite de supervision.

#### 6.7.3 Mutations Et Actions D'Administration

Le systeme peut aussi accompagner des actions de mise a jour ou de transformation, ce qui elargit notablement le role du chat admin.

#### 6.7.4 Workflows Complexes Et Multi-Taches

La prise en charge de demandes composees represente un gain important en souplesse et en richesse fonctionnelle.

#### 6.7.5 Securisation Des Interactions Sensibles

Les operations sensibles sont mieux encadrees, ce qui rend l'administration plus sure et plus credible dans une perspective de deploiement futur.

#### 6.7.6 Experience Utilisateur Admin Amelioree

Les ameliorations de rendu, de fluidite et de responsivite donnent au volet admin une meilleure qualite percue et une utilisation plus confortable.

### 6.8 Retrospective Du Sprint 4

Le sprint 4 a fait franchir a `Synapse` une etape de maturite importante. La plateforme n'est plus seulement une solution RAG modulaire ; elle devient aussi un environnement d'administration intelligent, capable de coordonner plusieurs services et de mieux assister l'administrateur dans ses taches. Cette evolution ouvre la voie a des usages plus complexes et a une architecture de plus en plus orientee vers l'agentification.

Elements visuels utiles a inserer en fin de chapitre :

- `[Tableau de synthese des nouvelles fonctionnalites admin]`
- `[Capture d'ecran du chat admin intelligent]`
- `[Capture d'ecran d'un workflow multi-etapes ou d'une reponse d'inspection]`
- `[Encadre de conclusion du sprint]`

---

## Conseils Pour La Version LaTeX

Pour obtenir un rendu proche de la table des matieres que tu as partagee, vous pouvez :

1. transformer chaque sprint en `\chapter{}`
2. transformer chaque bloc principal en `\section{}`
3. transformer chaque sous-bloc en `\subsection{}`, `\subsubsection{}` et, si besoin, `\paragraph{}`
4. inserer les diagrammes en figures dans les sections de conception
5. garder les details tres techniques dans des annexes si le chapitre devient trop long

## Raccourci Pratique

Si vous voulez un plan minimal mais academique, chaque sprint peut garder cette structure :

1. Introduction
2. Backlog du sprint
3. Etude technique
4. Choix technologiques
5. Conception
6. Realisation
7. Fonctionnalites developpees
8. Retrospective
