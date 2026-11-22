"""Read and standardize hospital data from Databricks SQL."""

import os
import re
from functools import lru_cache
from math import isfinite
from urllib.parse import urlsplit

from ranking import EQUIPMENT, TARGETS


FACILITY_TABLE = "workspace.default.careproof_facilities_serving"
EVIDENCE_TABLE = "workspace.default.careproof_facility_evidence_serving"


class DataSetupError(RuntimeError):
    """A data configuration issue that can be shown on the page."""


# Section 1. SQL identifiers and row conversion

def identifier(value):
    parts = value.split(".")

    if len(parts) != 3 or not all(
        re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part)
        for part in parts
    ):
        raise DataSetupError("Serving table names must use catalog.schema.table.")

    return ".".join(f"`{part}`" for part in parts)


def read_rows(cursor, table):
    cursor.execute(f"SELECT * FROM {identifier(table)}")
    columns = [description[0].lower() for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def first_value(row, *keys):
    return next((row[key] for key in keys if row.get(key) is not None), None)


def finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return number if isfinite(number) else None


def is_reported(value):
    return str(value).strip().lower() in {"reported", "true", "1", "1.0"}


# Section 2. Hospital coordinates, counts, and reported offerings

def prepare_hospitals(facilities, evidence):
    hospitals = {}

    for row in facilities:
        key = first_value(row, "facility_id", "hospital_id", "id")
        name = first_value(row, "facility_name", "hospital_name", "name")
        latitude = finite_number(
            first_value(row, "latitude_clean", "latitude", "lat")
        )
        longitude = finite_number(
            first_value(row, "longitude_clean", "longitude", "lon", "lng")
        )

        if key is None or not name or latitude is None or longitude is None:
            continue
        if abs(latitude) > 90 or abs(longitude) > 180:
            continue

        wide_codes = set(EQUIPMENT)
        wide_codes.update(
            column.removesuffix("_status")
            for column in row
            if column.startswith("specialty_")
        )

        offerings = {
            code for code in wide_codes
            if is_reported(first_value(row, f"{code}_status", code))
        }

        counts = {}
        for code in TARGETS:
            value = finite_number(row.get(code))
            if value is not None and value >= 0:
                counts[code] = value

        tier = first_value(
            row, "matrix_tier", "record_quality_tier", "credibility_tier", "tier"
        )

        hospitals.setdefault(str(key), {
            "id": str(key),
            "name": str(name),
            "latitude": latitude,
            "longitude": longitude,
            "tier": str(tier or "unknown").lower(),
            "reported": offerings,
            "counts": counts,
        })

    for row in evidence:
        key = first_value(row, "facility_id", "hospital_id", "id")
        hospital = hospitals.get(str(key))
        feature = first_value(
            row, "feature", "feature_code", "facility_feature",
            "service_code", "equipment_code",
        )
        status = first_value(
            row, "status", "evidence_status", "feature_status", "evidence_state",
        )
        category = str(first_value(row, "category", "feature_category") or "").lower()

        if hospital is None or not isinstance(feature, str) or not is_reported(status):
            continue

        code = feature.strip().lower()
        is_offering = (
            code in EQUIPMENT
            or code.startswith("specialty_")
            or category in {"facilities", "services", "equipment", "departments"}
        )

        if re.fullmatch(r"[a-z][a-z0-9_]*", code) and is_offering:
            hospital["reported"].add(code)

    if not hospitals:
        raise DataSetupError("No usable hospital records with valid coordinates were found.")

    departments = sorted({
        code
        for hospital in hospitals.values()
        for code in hospital["reported"]
        if code.startswith("specialty_")
    })

    if not departments:
        raise DataSetupError(
            "No reported specialty codes were found. Check the serving tables "
            "or configure CAREPROOF_DEPARTMENT_TABLE."
        )

    return list(hospitals.values()), departments


# Section 3. Read-only Databricks connection

@lru_cache(maxsize=1)
def snapshot():
    from databricks import sql
    from databricks.sdk.core import Config

    warehouse = os.environ.get("CAREPROOF_WAREHOUSE_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", warehouse):
        raise DataSetupError("Set CAREPROOF_WAREHOUSE_ID to the App SQL Warehouse resource.")

    config = Config()
    host = urlsplit(config.host).hostname

    with sql.connect(
        server_hostname=host,
        http_path=f"/sql/1.0/warehouses/{warehouse}",
        credentials_provider=lambda: config.authenticate,
    ) as connection:
        with connection.cursor() as cursor:
            facilities = read_rows(
                cursor, os.environ.get("CAREPROOF_FACILITY_TABLE") or FACILITY_TABLE
            )
            evidence = read_rows(
                cursor, os.environ.get("CAREPROOF_EVIDENCE_TABLE") or EVIDENCE_TABLE
            )

            department_table = os.environ.get("CAREPROOF_DEPARTMENT_TABLE")
            if department_table:
                evidence.extend(read_rows(cursor, department_table))

    return prepare_hospitals(facilities, evidence)