# Rapport Des Sprints

Ce document presente une version epuree du rapport des sprints, centree uniquement sur le contenu redactionnel des sprints du projet `Synapse`.

Hypotheses retenues :

- duree d'un sprint : `3 semaines`
- date de depart du projet : `26/02/2026`
- decoupage base sur l'historique Git du depot `nessimhjaiej/Agent`
- presence d'un sprint precedent non detaille ici, ce qui decale la numerotation de `+1`

Decoupage adopte dans le rapport :

1. `Sprint 2 : 26/02/2026 -> 18/03/2026`
2. `Sprint 3 : 19/03/2026 -> 08/04/2026`
3. `Sprint 4 : 09/04/2026 -> 29/04/2026`

---

# Chapitre 4

## Etude Et Realisation Sprint 2 : Mise En Place Du Socle Technique, De L'Integration Initiale Et De La Premiere Version Fonctionnelle

### 4.1 Introduction

Le sprint 2 correspond a la vraie phase de fondation technique de `Synapse`. Durant cette periode, l'objectif n'etait pas encore d'affiner l'experience utilisateur ou d'introduire des mecanismes d'orchestration avances, mais plutot de construire une base fiable sur laquelle les evolutions futures pourraient reposer. L'equipe s'est donc concentree sur la structuration du depot, la definition d'une architecture microservices, l'installation des premiers services backend et la mise en place d'un premier cycle complet allant de l'authentification jusqu'a la generation de reponse.

Ce sprint a egalement joue un role important dans la clarification de la vision du projet. A ce stade, il fallait valider que `Synapse` etait capable de gerer des documents, d'extraire leur contenu, d'indexer les passages utiles, puis de produire une reponse contextualisee a partir d'une question utilisateur. Il fallait aussi verifier que les differentes briques du projet pouvaient effectivement fonctionner ensemble, aussi bien cote backend que cote frontend. En d'autres termes, ce sprint a permis de passer d'une idee d'architecture a une premiere version executable et integree du systeme.

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
- evolution de la gestion des utilisateurs et des parcours d'authentification
- premiers ajustements sur l'experience de chat

### 4.3 Etude Technique Du Sprint 2

#### 4.3.1 Etude De L'Architecture Microservices

Le choix d'une architecture microservices repondait a un besoin de modularite et de separation claire des responsabilites. Chaque service prend en charge une etape bien precise du cycle de traitement : authentification, ingestion, pretraitement, embeddings, recherche ou generation. Cette approche facilite la maintenance, permet de faire evoluer un composant sans remettre en cause l'ensemble du systeme, et rend l'architecture plus lisible dans un contexte de projet de fin d'etudes.

#### 4.3.2 Etude Du Flux Documentaire Initial

Le flux documentaire initial commence par le depot d'un document, suivi de son stockage et de l'enregistrement de ses metadonnees. Les operations de traitement et d'indexation s'appuient ensuite sur les services dedies au preprocessing et aux embeddings, qui preparent les passages puis produisent les representations vectorielles necessaires a la recherche. Cette chaine est essentielle, car elle conditionne directement la qualite de la recherche et donc la pertinence des reponses generees.

#### 4.3.3 Etude Du Flux Question-Reponse

Le flux question-reponse repose sur une logique RAG classique. Lorsqu'un utilisateur pose une question, le systeme interroge d'abord la base vectorielle afin de recuperer les passages les plus pertinents. Ces passages sont ensuite injectes dans le contexte de generation, ce qui permet au modele de produire une reponse plus fiable, plus ciblee et mieux fondee sur le contenu documentaire reel.

#### 4.3.4 Etude De L'Authentification Et De La Gestion Des Roles

Des le debut du projet, il etait necessaire de distinguer les espaces d'usage entre les utilisateurs classiques et l'administrateur de `Synapse`. L'etude a donc porte sur la gestion des sessions, la protection des routes et l'association entre l'identite authentifiee et les droits disponibles dans l'application. Cette base etait indispensable pour preparer les evolutions des sprints suivants.

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

L'architecture generale du sprint 2 repose sur un decoupage clair entre les services documentaires, les services de recherche et de generation, ainsi que les composants transverses comme l'authentification et le stockage. Cette organisation permet de suivre plus facilement le parcours complet d'un document et celui d'une question utilisateur.

Emplacement recommande dans le memoire :

- Figure : architecture generale du sprint 2
- Illustration : vue globale de Synapse et de ses microservices

#### 4.5.3 Diagramme Use Case Du Sprint 2

Le diagramme de cas d'utilisation du sprint 2 met en evidence les interactions principales entre les acteurs et la plateforme, notamment l'acces aux fonctions documentaires, la consultation des reponses et les actions d'administration de base.

Emplacement recommande dans le memoire :

- Figure : diagramme de cas d'utilisation du sprint 2

#### 4.5.4 Diagrammes De Sequence Du Sprint 2

Les diagrammes de sequence servent a expliciter les premiers flux critiques du systeme, en particulier l'authentification, l'ingestion documentaire et la chaine de question-reponse.

Emplacement recommande dans le memoire :

- Figure : sequence d'authentification
- Figure : sequence d'ingestion documentaire
- Figure : sequence question-reponse du pipeline RAG

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

Le service d'ingestion prend en charge les operations documentaires de base, notamment le depot des fichiers, leur stockage, la gestion des metadonnees et la mise a jour de leur etat dans le systeme. Il constitue le point d'entree du cycle documentaire, sans porter a lui seul toute la logique d'indexation.

#### 4.6.7 Frontend Et Integration Initiale

Le frontend a servi de point d'entree unique pour les utilisateurs et l'administrateur. Durant ce sprint, l'effort a surtout porte sur l'integration des premiers appels backend et sur la validation d'un parcours fonctionnel complet.

### 4.7 Fonctionnalites Developpees Dans Le Sprint 2

#### 4.7.1 Authentification Et Gestion Des Utilisateurs

Une premiere gestion des comptes utilisateurs a ete mise en place afin de controler l'acces a `Synapse`. Cette fonctionnalite couvre la connexion, la persistance minimale des sessions et la distinction entre les droits d'un utilisateur classique et ceux d'un administrateur.

#### 4.7.2 Upload Et Indexation Des Documents

Le systeme est devenu capable de recevoir des documents, de les enregistrer, de les preparer puis de les indexer. Cette fonctionnalite constitue une brique centrale, car elle alimente directement la base de connaissances exploitee ensuite par le systeme RAG.

#### 4.7.3 Recherche Et Generation De Reponses

La recherche documentaire et la generation de reponses ont ete reliees dans un premier pipeline fonctionnel. L'utilisateur peut ainsi poser une question, obtenir une reponse contextualisee et beneficier d'un systeme fonde sur des passages reels extraits des documents.

#### 4.7.4 Tableau De Bord Initial Admin / User

Les premiers espaces d'interaction de `Synapse` ont ete rendus operationnels, aussi bien pour l'utilisateur final que pour l'administrateur. Meme si l'interface restait encore simple, elle permettait deja de tester les parcours essentiels du projet.

#### 4.7.5 Mise En Place Des Tests Et De L'Environnement Docker

Afin de rendre le projet plus reproductible, un environnement conteneurise a ete introduit avec Docker Compose. Des premiers tests ont egalement ete ajoutes pour verifier le bon fonctionnement des services et reduire les risques de regression.

#### 4.7.6 Enrichissement Progressif Des Parcours Utilisateur

En fin de sprint, `Synapse` a aussi commence a gagner en confort d'utilisation avec des evolutions sur la gestion des comptes, l'invitation des utilisateurs et certains parcours d'authentification. Ces ajouts restent encore en construction, mais ils montrent que la plateforme n'etait deja plus seulement un assemblage technique.

Emplacement recommande dans le memoire :

- Illustration : environnement local / conteneurisation
- Illustration : captures des interfaces principales du sprint 2

### 4.8 Retrospective Du Sprint 2

Le sprint 2 a permis de transformer une idee architecturale en une premiere plateforme executable. Il a confirme la pertinence du decoupage microservices, valide le fonctionnement general du pipeline RAG et montre qu'une integration reelle entre frontend, backend et services externes etait possible. En revanche, cette premiere version a aussi mis en lumiere plusieurs besoins de consolidation, notamment autour de la stabilite des sessions, de la lisibilite des donnees documentaires, de la supervision administrative et de l'experience utilisateur. Ces constats ont naturellement oriente le travail du sprint suivant.

---

# Chapitre 5

## Etude Et Realisation Sprint 3 : Conception D'Un Prototype Agentique D'Administration Pour Synapse

### 5.1 Introduction

Le sprint 3 a marque un changement important dans l'orientation du projet. Apres avoir pose les bases du systeme RAG et de son architecture microservices, l'equipe a travaille sur deux axes complementaires. D'une part, la branche principale a apporte plusieurs corrections et ameliorations necessaires pour rendre `Synapse` plus stable, plus coherent et plus agreable a utiliser. D'autre part, la branche `admin-agentic` a servi de terrain d'experimentation pour concevoir un prototype agentique dedie a l'administration de la plateforme.

Cette phase a donc combine un travail de consolidation et un travail d'innovation. Elle a permis, d'un cote, d'integrer des correctifs lies a l'authentification, aux sessions et a certaines fonctionnalites d'administration, et, de l'autre, de demarrer la construction du `admin-service`, de tester une premiere logique d'agent recursif, d'introduire un fast path pour certaines demandes frequentes et de mieux formaliser l'architecture cible a travers des diagrammes, des specifications d'API et une documentation plus claire. Ce sprint a ainsi joue le role de passerelle entre un systeme RAG fonctionnel et une vision plus intelligente de l'administration.

### 5.2 Backlog Du Sprint 3

Les principales taches de ce sprint peuvent etre presentees comme suit :

- integration des correctifs issus de la branche principale
- amelioration de certaines fonctionnalites admin existantes
- ajustements autour de l'authentification et de l'experience utilisateur
- integration de la transcription dans les parcours d'usage
- demarrage du `admin-service`
- conception d'un prototype d'administration agentique
- experimentation d'un agent recursif
- ajout d'un fast path pour les questions administratives frequentes
- formalisation des premiers cas d'usage admin intelligents
- clarification de l'architecture cible du module admin
- production de diagrammes de conception plus explicites
- redaction de specifications d'API pour les services lies a l'administration
- ajustement de l'infrastructure et de la documentation projet
- preparation des evolutions futures vers une orchestration plus complete

### 5.3 Etude Approfondie Du Systeme Au Sprint 3

#### 5.3.1 Etude De La Consolidation Du Systeme

Le sprint 3 ne s'est pas limite a la conception d'un prototype. Il a egalement integre un ensemble de correctifs et d'ameliorations provenant de la branche principale. Ce travail de consolidation etait indispensable pour continuer a faire evoluer `Synapse` sans fragiliser l'existant.

##### 5.3.1.1 Corrections Fonctionnelles Cote Administration

Certaines fonctionnalites admin ont ete corrigees ou ajustees afin d'assurer un comportement plus coherent de la plateforme. Ces corrections ont contribue a rendre les parcours deja disponibles plus fiables avant l'introduction d'une couche agentique plus ambitieuse.

##### 5.3.1.2 Stabilisation De L'Experience Utilisateur

Les ajustements menes sur la branche principale ont egalement participe a une meilleure fluidite d'utilisation, notamment autour de l'authentification, du comportement de l'interface et de la coherence generale des interactions.

##### 5.3.1.3 Integration De La Transcription

Le sprint 3 a aussi marque l'apparition plus concrete de la transcription dans l'experience utilisateur. Cette integration a contribue a rendre les interactions avec `Synapse` plus naturelles et a ouvrir la voie a des usages conversationnels plus souples.

#### 5.3.2 Etude Du Concept D'Administration Agentique

L'idee d'une administration agentique repose sur un principe simple : l'espace d'administration ne doit plus se limiter a des boutons ou a des formulaires statiques, mais devenir capable de comprendre une intention, de choisir une action adaptee et d'assister l'administrateur de maniere plus fluide. Cette reflexion a pousse l'equipe a etudier comment un agent pouvait intervenir dans des taches de supervision, d'explication ou d'orientation.

##### 5.3.2.1 Difference Entre Chat RAG Et Agent D'Administration

Un chat RAG classique a pour objectif principal de repondre a une question a partir de documents. A l'inverse, un agent d'administration doit pouvoir interpreter une demande plus operationnelle, raisonner sur l'etat du systeme et eventuellement mobiliser plusieurs operations pour produire une reponse utile.

##### 5.3.2.2 Besoin D'Un Espace Admin Plus Intelligent

Au fil de l'avancement de `Synapse`, il est devenu evident que l'administration du systeme allait depasser la simple gestion manuelle des documents et des utilisateurs. Un prototype intelligent permettait donc d'explorer une interface plus naturelle pour piloter la plateforme.

#### 5.3.3 Etude D'Une Logique D'Agent Recursif

L'un des axes d'experimentation de ce sprint a ete l'etude d'un agent recursif. Cette logique consiste a permettre au systeme de decomposer une demande complexe en plusieurs etapes de raisonnement ou de verification, plutot que de tenter de produire une reponse en une seule passe.

##### 5.3.3.1 Decomposition D'Une Demande Complexe

Certaines demandes administratives ne peuvent pas etre traitees par une simple reponse directe. Elles necessitent une lecture du contexte, une selection d'outils ou une verification intermediaire. L'agent recursif represente une premiere piste pour gerer ce type de cas.

##### 5.3.3.2 Limites D'Une Approche Entierement Generique

Cette experimentation a egalement montre qu'une approche totalement libre pouvait etre couteuse et parfois peu previsible. C'est pour cette raison qu'un mecanisme plus direct a aussi ete envisage pour les demandes frequentes.

#### 5.3.4 Etude Du Fast Path Pour Les Requetes Courantes

Le fast path correspond a une voie de traitement rapide pour certaines questions ou intentions recurrentes. L'idee est d'eviter un raisonnement trop lourd quand une reponse simple, guidee ou predefinie peut suffire.

##### 5.3.4.1 Reduction Du Cout De Traitement

En orientant rapidement les demandes les plus simples, il devient possible de diminuer le temps de reponse et de rendre l'interface admin plus reactive.

##### 5.3.4.2 Amelioration De La Lisibilite Fonctionnelle

Le fast path permet aussi de mieux structurer les comportements du systeme. Il aide a distinguer les cas simples, traitables directement, des cas plus riches qui necessitent un raisonnement plus approfondi.

#### 5.3.5 Etude De La Formalisation Architecturale

Ce sprint a egalement ete marque par un effort de formalisation. A mesure que la vision agentique prenait forme, il devenait necessaire de mieux documenter les interactions, les cas d'usage et les API afin de rendre la solution plus compréhensible et plus partageable au sein de l'equipe.

### 5.4 Choix Technologiques Et Evolutions Retenues

#### 5.4.1 Choix D'Un Prototype Separe Pour L'Administration

L'equipe a fait le choix de demarrer un service specifique pour l'administration plutot que d'integrer cette logique directement dans les services RAG existants. Cette decision permettait d'isoler les experimentations agentiques sur la branche `admin-agentic` tout en preservant la stabilite du reste du systeme sur la branche principale.

#### 5.4.2 Choix D'Une Approche Progressive De L'Agent

Plutot que de construire immediatement une orchestration complexe, le sprint 3 a privilegie une approche progressive : commencer par un prototype simple, tester une logique recursive, puis introduire des mecanismes de routage plus directs comme le fast path.

#### 5.4.3 Choix De Renforcer La Documentation Technique

La production de diagrammes, de schemas et de specifications d'API a ete retenue comme un axe important du sprint. Ce travail etait necessaire pour rendre la future architecture agentique plus claire, plus defendable et plus facile a faire evoluer.

### 5.5 Conception De L'Architecture Du Sprint 3

#### 5.5.1 Objectifs De La Nouvelle Architecture

Les objectifs de cette evolution architecturale etaient les suivants :

- consolider la base existante avant d'introduire des comportements plus avances
- introduire un premier prototype d'administration intelligente
- separer la logique admin agentique du pipeline RAG principal
- explorer un raisonnement multi-etapes pour certaines demandes
- preparer l'orchestration plus complete du sprint suivant

#### 5.5.2 Architecture Generale Sprint 3

L'architecture du sprint 3 conserve le socle microservices de `Synapse`, tout en evoluant sur deux plans. Le premier correspond a la consolidation du systeme existant sur la branche principale. Le second ajoute une nouvelle brique experimentale sur la branche `admin-agentic` : le `admin-service`. Ce service commence a jouer le role d'intermediaire intelligent entre l'interface d'administration, les informations du systeme et les futures actions outillees que l'agent devra pouvoir declencher.

Emplacement recommande dans le memoire :

- Figure : architecture generale du sprint 3
- Illustration : schema de transition entre correctifs du socle et prototype admin agentique

#### 5.5.3 Diagramme Use Case Du Sprint 3

Le diagramme de cas d'utilisation du sprint 3 met cette fois l'accent sur les interactions entre l'administrateur et le prototype agentique, tout en conservant les fonctionnalites admin deja consolidees sur la branche principale.

Emplacement recommande dans le memoire :

- Figure : diagramme de cas d'utilisation du sprint 3

#### 5.5.4 Diagramme Du Prototype D'Administration

Un diagramme de sequence ou d'activite peut utilement illustrer le fonctionnement du prototype, notamment la reception d'une demande admin, le passage par une logique de selection, puis le retour d'une reponse ou d'une orientation adaptee.

Emplacement recommande dans le memoire :

- Figure : sequence du prototype d'administration
- Illustration : capture d'un ecran admin ou du chat prototype

### 5.6 Mise En Place Des Evolutions Du Sprint 3

#### 5.6.1 Integration Des Correctifs De La Branche Principale

Une partie importante du sprint a consiste a recuperer et integrer les correctifs issus de la branche principale. Ce travail a concerne plusieurs aspects de la plateforme, notamment certaines fonctionnalites d'administration, des ajustements d'interface et des ameliorations liees au comportement global du systeme.

#### 5.6.2 Integration De La Transcription Dans L'Interface

La transcription a ete ajoutee dans les parcours visibles du produit afin de permettre une interaction plus fluide avec la plateforme. Meme si cette fonctionnalite restait encore perfectible, elle representait deja une evolution notable de l'experience d'utilisation.

#### 5.6.3 Demarrage Du Admin-Service

L'une des avancees majeures du sprint a ete le lancement effectif du `admin-service`. Cette etape a permis de donner une existence concrete a l'idee d'une administration plus intelligente et de creer un espace dedie aux futures logiques agentiques.

#### 5.6.4 Construction Du Prototype Agentique

Le prototype a ete pense comme une premiere preuve de concept. Il ne s'agissait pas encore d'un agent completement mature, mais plutot d'une base experimentale capable de recevoir une demande d'administration, de l'interpreter et de renvoyer une premiere forme de reponse utile.

#### 5.6.5 Experimentation D'Un Agent Recursif

Le travail mene autour de l'agent recursif a permis de tester une logique de raisonnement plus souple. Cette experimentation est importante, car elle annonce directement les mecanismes d'orchestration plus structures qui seront approfondis par la suite.

#### 5.6.6 Ajout D'Un Fast Path

L'introduction d'un fast path pour certaines questions frequentes a contribue a rendre le prototype plus pragmatique. Ce choix a montre qu'une architecture agentique efficace ne repose pas uniquement sur le raisonnement profond, mais aussi sur la capacite a traiter rapidement les cas simples.

#### 5.6.7 Documentation Et Specifications

En parallele du travail de prototype, un effort important a ete fourni sur les diagrammes, les cas d'usage et les specifications d'API. Cette documentation a aide a clarifier la direction prise par `Synapse` et a structurer la suite du projet.

### 5.7 Fonctionnalites Developpees Dans Le Sprint 3

#### 5.7.1 Corrections Et Consolidation De La Plateforme

Le sprint 3 a d'abord permis de renforcer la base existante de `Synapse` grace a l'integration de correctifs provenant de la branche principale. Cette consolidation etait importante pour maintenir un produit exploitable pendant que les experimentations plus avancees etaient menees en parallele.

#### 5.7.2 Integration De La Transcription Dans L'Experience Utilisateur

L'ajout de la transcription a enrichi les modes d'interaction avec `Synapse`. Cette fonctionnalite a rendu l'utilisation du systeme plus accessible et plus naturelle, tout en preparant des evolutions futures autour des interfaces conversationnelles.

#### 5.7.3 Premiere Base Du Module D'Administration Intelligente

Le sprint 3 a permis de transformer une idee en premier module exploitable. Avec le demarrage du `admin-service`, `Synapse` ne se limite plus a un systeme RAG conversationnel ; la plateforme commence a se doter d'un espace admin plus intelligent.

#### 5.7.4 Prototype D'Agent Pour Le Raisonnement Administratif

La mise en place d'un prototype agentique constitue l'une des contributions les plus marquantes de ce sprint. Meme si cette version reste exploratoire, elle represente une etape concrete vers un assistant capable d'aider l'administrateur dans ses decisions et ses analyses.

#### 5.7.5 Traitement Recursif Des Demandes Complexes

L'experimentation de l'agent recursif a permis d'etudier la faisabilite d'un raisonnement en plusieurs etapes. Cette capacite est importante pour les demandes qui ne peuvent pas etre resolues par une simple reponse directe.

#### 5.7.6 Traitement Rapide Des Cas Simples

Avec le fast path, le systeme commence a distinguer les demandes simples des demandes plus complexes. Cette evolution contribue a une meilleure reactivite du prototype et montre deja une forme de maturite dans la conception.

#### 5.7.7 Documentation Plus Claire De L'Architecture Cible

Le travail de formalisation mene sur les diagrammes, les specifications et les schemas a facilite la comprehension du prototype et a pose des bases solides pour les evolutions du sprint 4.

### 5.8 Retrospective Du Sprint 3

Le sprint 3 a ete une phase de transition tres riche pour `Synapse`. Il a combine deux dynamiques complementaires : d'un cote, l'integration de correctifs et d'ameliorations issus de la branche principale ; de l'autre, l'ouverture d'une nouvelle direction produit avec la conception d'un prototype d'administration agentique. Le lancement du `admin-service`, l'experimentation de l'agent recursif et l'ajout d'un fast path ont permis de verifier que cette orientation etait realiste et pertinente.

Ce sprint reste volontairement exploratoire. Tout n'y etait pas encore finalise, mais il a permis de clarifier la vision, de valider des choix importants et de donner une forme concrete a l'idee d'un agent d'administration. En ce sens, il constitue le vrai point de depart de l'intelligence administrative qui sera approfondie et structuree dans le sprint 4.

---

# Chapitre 6

## Etude Et Realisation Sprint 4 : Administration Intelligente, Orchestration Agentique Et Optimisation Avancee

### 6.1 Introduction

Le sprint 4 marque une evolution majeure du projet. Alors que les deux sprints precedents ont permis de construire puis de stabiliser `Synapse`, cette nouvelle phase introduit une dimension plus intelligente et plus dynamique dans l'administration du systeme. L'objectif n'etait plus uniquement d'executer des flux documentaires ou d'afficher des informations, mais de permettre a l'espace admin de raisonner sur les demandes, de choisir une strategie d'action et de coordonner plusieurs outils ou services.

### 6.2 Backlog Du Sprint 4

Les principales taches de ce sprint peuvent etre resumees comme suit :

- integration de `LangGraph` dans `admin-service`
- mise en place d'une logique de classification des intentions
- ajout de branches d'execution : conseil, inspection, mutation
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

Cette sous-partie peut expliquer comment le systeme reconnait qu'une demande doit etre decomposee en plusieurs operations.

##### 6.3.2.2 Coordination Entre Outils Et Services

Une fois la demande decomposee, le systeme doit coordonner les services existants de maniere coherente. C'est ici que l'orchestration agentique prend tout son sens.

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

L'architecture du sprint 4 se distingue par une logique d'orchestration plus avancee, dans laquelle l'espace admin ne se contente plus de consommer des services, mais devient capable de piloter des actions, de choisir des branches de traitement et de coordonner plusieurs composants.

Emplacement recommande dans le memoire :

- Figure : architecture generale du sprint 4
- Figure : schema d'orchestration agentique de Synapse

#### 6.5.3 Diagramme Use Case Du Sprint 4

Le diagramme de cas d'utilisation du sprint 4 met en evidence les interactions propres a l'administration intelligente, notamment le chat admin, les fonctions d'inspection, les mutations, les workflows multi-etapes et les ajustements des parametres RAG.

Emplacement recommande dans le memoire :

- Figure : diagramme de cas d'utilisation du sprint 4

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

Le chat admin de `Synapse` ne se contente plus d'afficher des informations ; il devient un veritable point d'orchestration des actions et des analyses.

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

Emplacement recommande dans le memoire :

- Illustration : capture du chat admin intelligent
- Illustration : capture d'un workflow multi-etapes ou d'une reponse d'inspection

### 6.8 Retrospective Du Sprint 4

Le sprint 4 a fait franchir a `Synapse` une etape de maturite importante. La plateforme n'est plus seulement une solution RAG modulaire ; elle devient aussi un environnement d'administration intelligent, capable de coordonner plusieurs services et de mieux assister l'administrateur dans ses taches. Cette evolution ouvre la voie a des usages plus complexes et a une architecture de plus en plus orientee vers l'agentification.
