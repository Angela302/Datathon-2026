# CareProof

CareProof helps users compare nearby hospitals based on their location, the services they need, and their preferences. It shortlists up to **10 nearby hospitals**, ranks them, and displays the **top three recommendations** alongside the user’s starting point on an interactive map.

Built for the **CMU Fall 2026 Datathon** using the Virtue Foundation healthcare dataset.

## Data Cleaning and Feature Engineering

We used rule-based checks to classify hospital records into three reliability tiers: **Credible**, **Uncertain**, and **Unreliable**. We manually reviewed **26 records** and identified **two conflicts**. We then used the review results to train a **logistic regression model** for follow-up review.

We built a hierarchical feature tree to break **Distance**, **Personnel**, and **Facilities** into more detailed features, including **18 standardized facility indicators**. The resulting matrix has **one row per hospital and one column per feature**, so each hospital is represented as a point in an N-dimensional feature space. Record reliability is used as a separate criterion in the ranking.

## Recommendation Workflow

1. **Collect the user’s location and needs.** The user enters their latitude and longitude. They can describe their symptoms or select a department and services manually.
2. **Suggest search criteria with Databricks AI.** Our project workflow includes **Databricks Genie**. In the website code, the symptom suggestion feature calls a configured **Databricks Model Serving** endpoint to suggest **one department and up to three ranked equipment or service needs**. Users can review or change the suggestions before searching.
3. **Filter by department.** Keep hospitals whose records report the selected department.
4. **Find the 10 nearest neighbors.** Use a **K-nearest-neighbor search with K = 10** to shortlist eligible hospitals by straight-line distance from the user’s coordinates. Both ranking scenarios start with this same shortlist.
5. **Rank and display the Top 3.** Apply the default or personalized preferences and show up to three hospitals alongside the user’s starting point on an interactive map.

## Default and Personalized Ranking

The **Analytic Hierarchy Process (AHP)** provides the default weights for the four ranking categories.

| Category | Default weight |
|---|---:|
| Distance | 10.63% |
| Facilities | 63.40% |
| Personnel | 10.28% |
| Reliability | 15.69% |

Within **Facilities**, **Rank-Order Centroid (ROC)** gives more weight to higher-priority equipment or service needs. With three needs, the ROC proportions are **61.11%**, **27.78%**, and **11.11%**, in priority order.

The project design uses **PROMETHEE II for both default and personalized recommendations**. It compares candidates pair by pair and ranks them by their net advantage across the shortlist.

| Scenario | Preferences |
|---|---|
| **Default** | Use the four AHP category weights and the ROC proportions for the suggested needs. |
| **Personalized** | Use the user’s category weights and retain the ROC proportions for the suggested needs. Extra facility or personnel preferences are optional. Items already selected as primary needs are excluded from the extra options. |

**Current implementation on `main`:** The website runs PROMETHEE II when at least one extra preference is selected. Without extras, it calculates a weighted score using the active category weights. In the PROMETHEE II path, an extra-preference bonus of up to five points breaks ties in the primary score.

## Interactive Map

The website passes the **user’s starting coordinates** and the **ranked hospital records** directly to the embedded Leaflet map. The starting point has its own marker, and the hospitals are numbered by rank.

Users can pan, zoom, and click a hospital pin to see its **rank and distance**. An expandable section shows matched equipment, unconfirmed equipment, and reported services. The same map displays results from either ranking scenario.

## Run on Databricks

1. Open the [project Notebook](%28Clone%29%20Datathon.ipynb) in Databricks to review the data preparation and ranking analysis.
2. Use the [website folder](%28Clone%29%20CareProof_Web/) as the Databricks App source. It contains the application code, frontend, `app.yaml`, and dependencies.
3. Configure the App’s `sql-warehouse` and `model-endpoint` resources. Give the App read access to the hospital and evidence tables. The default tables are `workspace.default.careproof_facilities_serving` and `workspace.default.careproof_facility_evidence_serving`.
4. Deploy the app, open its URL, and run a search using a location, department, and one to three equipment or service needs. Compare the ranked list with the numbered pins on the map.

## Interpreting the Results

A **reported** service appears in the source data. An **unconfirmed** service has insufficient evidence in the dataset to establish availability. The reliability tier describes the quality of the hospital record. Map distances are straight-line estimates.
