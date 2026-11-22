# IA Trader : bot de trading crypto en simulation

Le bot démarre avec 100 € fictifs et trade tout seul avec les **vrais prix du marché** (Kraken). Objectif : 200 €.
Il tourne toutes les 15 minutes sur GitHub Actions, gratuitement, même quand ton PC est éteint. Tu le suis depuis ton iPhone sur un tableau de bord.

## Ce que fait le bot

- **Scan** chaque dimanche : il teste ses 2 stratégies sur toutes les cryptos en euros de Kraken, avec 2 ans d'historique en journalier et ~4 mois en bougies de 4 h. Il ne garde que les cryptos où une stratégie gagne sur les deux périodes, frais compris.
- **Stratégies**
  - *Départ après calme* : le prix dort, puis il casse vers le haut avec du volume.
  - *Suivi de tendance* : en tendance haussière, il achète quand le prix repasse au-dessus de sa moyenne après un creux.
- **Marché** : il lit 7 sites d'actus crypto, les posts de Trump sur Truth Social, l'indice Peur & Avidité et les positions des 30 meilleurs traders d'Hyperliquid (les baleines).
  - Si les actus s'affolent ou si Trump poste sur le marché, il met ses achats en pause pendant 2 h.
  - Il n'achète pas une crypto que les baleines vendent massivement.
- **Protection**
  - Chaque achat a un stop-loss et un stop suiveur qui sécurise les gains.
  - Il a au maximum 3 positions en même temps.
  - **Arrêt d'urgence** automatique à −30 % : il vend tout et s'arrête.
- **Réalisme** : la simulation compte 0,40 % de frais par ordre (le tarif Kraken Pro de base) et 0,10 % de glissement.

## Installation (une fois, sur ton PC ou ton Mac, ~10 min)

1. Sur github.com (compte `valentinperard78-code`) : **New repository**, nom `ia-trader`, **Public**, puis **Create**.
   Le dépôt doit être public pour que la page et les 15 minutes de calcul soient gratuites.
2. Dézippe le dossier, puis dans le dépôt : **uploading an existing file**. Glisse **tout le contenu** du dossier, y compris le dossier `.github`, puis **Commit changes**.
   Sur Mac, `.github` est caché : appuie sur Cmd + Maj + . dans le Finder pour le voir.
3. **Settings → Actions → General → Workflow permissions** : coche **Read and write permissions**, puis **Save**.
4. **Settings → Pages** : Source **Deploy from a branch**, branche `main`, dossier `/docs`, puis **Save**.
5. Onglet **Actions** : active les workflows si GitHub le demande.
   - Ouvre **Scan des cryptos**, puis **Run workflow**. Ça prend 20 à 40 min.
   - Ensuite, ouvre **Bot (toutes les 15 min)**, puis **Run workflow**.
6. Sur l'iPhone, ouvre `https://valentinperard78-code.github.io/ia-trader/` dans Safari, puis **Partager → Sur l'écran d'accueil**. Tu as ton appli.

## Régler le bot

Tout se règle dans `config.json`, avec le crayon ✏️ sur GitHub (ça marche aussi depuis l'appli GitHub mobile) :

- `budget_eur`, `objectif_eur` : le budget de départ et l'objectif
- `arret_urgence` : mets `true` pour tout vendre et arrêter, puis `false` pour relancer
- `pause_manuelle` : mets `true` pour bloquer les nouveaux achats
- `reset_id` : change le nombre (par exemple 1 → 2) pour **tout recommencer à zéro** avec le budget indiqué
- `positions_max`, `perte_max_avant_arret_pct` : le niveau de risque

## Bon à savoir

- C'est une **simulation** : aucun argent réel n'est en jeu, et aucune clé API n'est nécessaire.
- Les horaires de GitHub peuvent avoir quelques minutes de retard.
- Les stops sont vérifiés à chaque passage du bot (environ toutes les 15 min), pas à la seconde. En argent réel, on les placerait directement chez Kraken.
- Si un site d'actus ou le flux de Trump ne répond pas, le bot continue sans lui.
- Laisse la simulation tourner **au moins 1 à 2 mois** avant de juger. Quelques bons jours ne prouvent rien.
- Tests hors ligne : `python -m tests.test_offline`
