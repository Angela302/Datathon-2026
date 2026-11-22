"""Hospital eligibility, distance, and ranking calculations."""

from itertools import combinations
from math import asin, cos, exp, isfinite, log, radians, sin, sqrt


# Section 1. Ranking criteria and available preference options

CRITERIA = ("distance", "facilities", "personnel", "reliability")

EQUIPMENT = (
    "emergency_24_7",
    "dental_emergency_24_7",
    "mri_equipment",
    "mri_scan",
    "ct_scanner",
    "ct_scan",
    "blood_draw",
    "dialysis_machine",
    "hemodialysis",
    "peritoneal_dialysis",
    "ventilator",
    "ultrasound_equipment",
    "ultrasound_scan",
    "xray_equipment",
    "nicu",
    "icu",
    "cesarean_delivery",
)

FACILITIES = ("reported_capacity", *EQUIPMENT)

PERSONNEL = (
    "doctor_count",
    "nurse_count",
    "specialist_count",
    "midwife_count",
    "technician_count",
    "total_staff_count",
)

TARGETS = {
    "reported_capacity": 200,
    "doctor_count": 50,
    "nurse_count": 100,
    "specialist_count": 25,
    "midwife_count": 10,
    "technician_count": 25,
    "total_staff_count": 200,
}

RELIABILITY = {"credible": 1.0, "uncertain": 0.5, "unreliable": 0.0}


# Section 2. AHP defaults from the original survey responses

AHP_RESPONSES = (
    (-5, 3, -3, 7, 5, -3),
    (-5, -5, -3, 3, 5, 3),
    (-5, 3, 1, 7, 7, -3),
)


def normalize(weights):
    if any(not isfinite(value) or value < 0 for value in weights.values()):
        raise ValueError("Weights must be finite and nonnegative.")

    total = sum(weights.values())
    if not isfinite(total) or total <= 0:
        raise ValueError("At least one ranking weight must be greater than zero.")

    return {key: value / total for key, value in weights.items()}


def ahp_weights():
    size = len(CRITERIA)
    matrix = [[1.0] * size for _ in range(size)]

    for (left, right), ratings in zip(
        combinations(range(size), 2), zip(*AHP_RESPONSES)
    ):
        mean_log = sum(
            log(rating) if rating > 0 else -log(-rating)
            for rating in ratings
        ) / len(ratings)
        ratio = exp(mean_log)
        matrix[left][right] = ratio
        matrix[right][left] = 1 / ratio

    weights = [1 / size] * size

    for _ in range(1000):
        product = [
            sum(value * weight for value, weight in zip(row, weights))
            for row in matrix
        ]
        total = sum(product)
        updated = [value / total for value in product]

        if max(abs(a - b) for a, b in zip(weights, updated)) < 1e-12:
            return dict(zip(CRITERIA, updated))

        weights = updated

    raise RuntimeError("AHP weights did not converge.")


DEFAULT_WEIGHTS = ahp_weights()


# Section 3. Department eligibility and nearby hospitals

def distance_km(latitude, longitude, hospital_latitude, hospital_longitude):
    start = radians(latitude)
    end = radians(hospital_latitude)

    haversine = (
        sin((end - start) / 2) ** 2
        + cos(start)
        * cos(end)
        * sin(radians(hospital_longitude - longitude) / 2) ** 2
    )

    return 12742 * asin(sqrt(min(1.0, max(0.0, haversine))))


def nearest(hospitals, department, latitude, longitude):
    candidates = [
        {
            **hospital,
            "distance_km": distance_km(
                latitude,
                longitude,
                hospital["latitude"],
                hospital["longitude"],
            ),
        }
        for hospital in hospitals
        if department in hospital["reported"]
    ]

    return sorted(
        candidates,
        key=lambda row: (row["distance_km"], row["id"]),
    )[:10]


# Section 4. ROC equipment weights and PROMETHEE II primary scores

def roc_weights(equipment):
    count = len(equipment)

    return {
        code: sum(1 / position for position in range(index, count + 1)) / count
        for index, code in enumerate(equipment, start=1)
    }


def satisfaction(hospital, code):
    if code in TARGETS:
        value = hospital["counts"].get(code)
        return min(1.0, value / TARGETS[code]) if value is not None else 0.0

    return float(code in hospital["reported"])


def promethee_scores(values, weights):
    net_totals = [0.0] * len(values)

    for left, right in combinations(range(len(values)), 2):
        advantage = 0.0

        for criterion, weight in weights.items():
            a = values[left][criterion]
            b = values[right][criterion]
            advantage += weight * ((a > b) - (a < b))

        net_totals[left] += advantage
        net_totals[right] -= advantage

    opponents = max(1, len(values) - 1)
    return [
        min(100.0, max(0.0, 50 * (1 + total / opponents)))
        for total in net_totals
    ]


# Section 5. Optional preference bonus and final ordering

def preference_weights(preferences, category_weights):
    selected = set(preferences)
    groups = {
        "facilities": selected & set(FACILITIES),
        "personnel": selected & set(PERSONNEL),
    }
    active = {
        category: category_weights[category]
        for category, items in groups.items()
        if items
    }

    if sum(active.values()) <= 0:
        return {}

    shares = normalize(active)
    return {
        code: shares[category] / len(groups[category])
        for category in shares
        for code in sorted(groups[category])
    }


def rank(candidates, equipment, preferences, category_weights):
    weights = normalize(category_weights)
    roc = roc_weights(equipment)
    values = []

    for hospital in candidates:
        equipment_values = {
            code: satisfaction(hospital, code) for code in equipment
        }
        values.append({
            "distance": max(0.0, 1 - hospital["distance_km"] / 50),
            "facilities": sum(roc[code] * value for code, value in equipment_values.items()),
            "personnel": satisfaction(hospital, "doctor_count"),
            "reliability": RELIABILITY.get(hospital["tier"], 0.0),
            **equipment_values,
        })

    if preferences:
        primary_weights = {
            category: weights[category]
            for category in CRITERIA
            if category != "facilities"
        }
        primary_weights.update({
            code: weights["facilities"] * share
            for code, share in roc.items()
        })
        scores = promethee_scores(values, primary_weights)
    else:
        scores = [
            100 * sum(weights[category] * row[category] for category in CRITERIA)
            for row in values
        ]

    bonus_weights = preference_weights(preferences, weights)
    results = []

    for hospital, score in zip(candidates, scores):
        bonus = min(5.0, 5 * sum(
            weight * satisfaction(hospital, code)
            for code, weight in bonus_weights.items()
        ))

        results.append({
            **{
                key: hospital[key]
                for key in ("id", "name", "latitude", "longitude", "tier")
            },
            "distance_km": hospital["distance_km"],
            "primary_score": round(score, 10),
            "bonus": round(bonus, 10),
            "equipment": [
                {"code": code, "reported": code in hospital["reported"]}
                for code in equipment
            ],
        })

    return sorted(results, key=lambda row: (
        -row["primary_score"],
        -row["bonus"],
        row["distance_km"],
        row["id"],
    ))