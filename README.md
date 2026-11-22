# CareProof

CareProof helps users compare nearby hospitals based on their location, the services they need, and their preferences. It finds up to **10 nearby hospitals** that report the selected department, ranks them, and displays the **top three** alongside the user’s starting point on an interactive map.

Built for the **CMU Fall 2026 Datathon** using the Virtue Foundation healthcare dataset.

## Data Cleaning and Feature Engineering

We applied rule-based checks to classify hospital records into three data reliability tiers: **Credible**, **Uncertain**, and **Unreliable**. We manually reviewed **26 records** and identified **two conflicts**. We used the manual review results to train a logistic regression model for follow-up review.

We then built a hierarchical feature tree to break **Distance**, **Personnel**, and **Facilities** into more detailed features. The resulting feature matrix has one row per hospital and one column per feature. Each hospital is represented as a point in an N-dimensional feature space. Record reliability is used as a separate ranking criterion.

## Recommendation Workflow

1. **Enter a location and search criteria.** Users provide their latitude and longitude. They can select a department and services manually or describe their symptoms and ask a configured Databricks model endpoint to suggest **one department and one to three ranked equipment or service needs**.
2. **Find nearby hospitals.** CareProof filters for hospitals that report the selected department and keeps the **10 closest** by straight-line distance. Equipment and service matches are used in ranking and shown in the results.
3. **Rank the shortlist.** CareProof uses four categories: **Distance, Facilities, Personnel, and Reliability**. Users can adjust these weights and optionally select additional facility or personnel preferences.
4. **Show the Top 3.** The website sends the ranked hospitals and the user’s starting coordinates directly to the embedded Leaflet map. Numbered pins show the current rank, and users can click a hospital to see its distance and service details.

## Ranking and Preferences

The **Analytic Hierarchy Process (AHP)** provides the default category weights.

| Category | Default weight |
|---|---:|
| Distance | 10.63% |
| Facilities | 63.40% |
| Personnel | 10.28% |
| Reliability | 15.69% |

Within Facilities, **Rank-Order Centroid (ROC)** gives more weight to higher-priority equipment or services. With three items, the weights are **61.11%**, **27.78%**, and **11.11%**.

| User choices | Ranking method |
|---|---|
| Default weights, no extra preferences | Weighted score using the AHP defaults |
| Custom weights, no extra preferences | Weighted score using the user’s category weights |
| One or more extra preferences | **PROMETHEE II** pairwise ranking using the active category weights. An extra-preference bonus of up to five points breaks ties in the primary score. |

Extra preferences can include facility and personnel indicators. Equipment already selected as a primary need is excluded from the extra options.

## Run on Databricks

1. Open the [project Notebook](%28Clone%29%20Datathon.ipynb) in Databricks to inspect the data preparation and ranking analysis.
2. Use the [website folder](%28Clone%29%20CareProof_Web/) as the Databricks App source. It includes the application code, frontend, `app.yaml`, and dependencies.
3. Configure the App’s `sql-warehouse` and `model-endpoint` resources. Give the App permission to read the hospital and evidence tables. By default, the app reads `workspace.default.careproof_facilities_serving` and `workspace.default.careproof_facility_evidence_serving`.
4. Deploy the app, open its URL, and try a search with a location, department, and one to three services. Check the ranked hospital list and the corresponding map pins.

## Interpreting the Results

A **reported** service appears in the source data. An **unconfirmed** service has insufficient evidence in the dataset to establish availability. The reliability tier describes the quality of the hospital record, and the distance shown is a straight-line estimate.
