import psycopg2

# ===== НАСТРОЙКИ ПОДКЛЮЧЕНИЯ =====

conn = psycopg2.connect(
    host='localhost',
    port='5432',
    dbname='gh_houses',
    user='admin',
    password='admin'
)
conn.autocommit = True
cur = conn.cursor()

# ===== ШАГ 1. Замена NaN на NULL в фактовой таблице =====
cur.execute("""
    UPDATE fact_houses SET deterioration = NULL WHERE deterioration = 'NaN';
    UPDATE fact_houses SET total_area = NULL WHERE total_area = 'NaN';
    UPDATE fact_houses SET latitude = NULL WHERE latitude = 'NaN';
    UPDATE fact_houses SET longitude = NULL WHERE longitude = 'NaN';
""")
print("Шаг 1: NaN заменены на NULL")

# ===== ШАГ 2. Витрина marts_houses_full =====
cur.execute("""
    DROP TABLE IF EXISTS marts_houses_full;
    CREATE TABLE marts_houses_full AS
    SELECT
        f.gisghk_id,
        f.full_address,
        r.region_name,
        m.municipality_name,
        f.postal_code,
        f.latitude,
        f.longitude,
        ht.house_type,
        hc.house_condition,
        f.building_year,
        f.comissioning_year,
        f.reconstruction_year,
        f.flats,
        f.total_area,
        f.residental_premises_area,
        f.deterioration,
        ec.energy_class_code,
        ec.energy_class_group,
        mo.management_organization_name,
        ls.life_cycle_stage,
        CASE
            WHEN f.deterioration < 20 THEN '0-20%'
            WHEN f.deterioration < 40 THEN '20-40%'
            WHEN f.deterioration < 60 THEN '40-60%'
            WHEN f.deterioration < 80 THEN '60-80%'
            ELSE '80-100%'
        END AS wear_bucket,
        CASE WHEN f.deterioration > 70 THEN 1 ELSE 0 END AS is_high_wear
    FROM fact_houses f
    LEFT JOIN dim_region r                 ON f.region_id = r.region_id
    LEFT JOIN dim_municipality m           ON f.municipality_id = m.municipality_id
    LEFT JOIN dim_house_type ht            ON f.house_type_id = ht.house_type_id
    LEFT JOIN dim_house_condition hc       ON f.house_condition_id = hc.house_condition_id
    LEFT JOIN dim_energy_efficency_class ec ON f.energy_class_id = ec.energy_class_id
    LEFT JOIN dim_management_organization mo ON f.management_organization_id = mo.management_organization_id
    LEFT JOIN dim_life_cycle_stage ls      ON f.life_cycle_stage_id = ls.life_cycle_stage_id;
""")
print("Шаг 2: marts_houses_full построена")

# ===== ШАГ 3. Витрина marts_by_year =====
cur.execute("""
    DROP TABLE IF EXISTS marts_by_year;
    CREATE TABLE marts_by_year AS
    SELECT
        f.building_year,
        COUNT(*) AS house_count,
        AVG(f.deterioration) AS avg_deterioration,
        AVG(CASE WHEN f.deterioration > 70 THEN 1 ELSE 0 END) AS share_high_wear,
        AVG(CASE WHEN hc.house_condition = 'Аварийный' THEN 1 ELSE 0 END) AS share_accident
    FROM fact_houses f
    LEFT JOIN dim_house_condition hc ON f.house_condition_id = hc.house_condition_id
    WHERE f.building_year IS NOT NULL
    GROUP BY f.building_year
    ORDER BY f.building_year;
""")
print("Шаг 3: marts_by_year построена")

# ===== ШАГ 4. Витрина marts_by_region =====
cur.execute("""
    DROP TABLE IF EXISTS marts_by_region;
    CREATE TABLE marts_by_region AS
    SELECT
        r.region_name,
        COUNT(*) AS house_count,
        SUM(f.total_area) AS total_area,
        AVG(f.deterioration) AS avg_deterioration,
        AVG(CASE WHEN f.deterioration > 70 THEN 1 ELSE 0 END) AS share_high_wear,
        AVG(CASE WHEN hc.house_condition = 'Аварийный' THEN 1 ELSE 0 END) AS share_accident
    FROM fact_houses f
    LEFT JOIN dim_region r                 ON f.region_id = r.region_id
    LEFT JOIN dim_house_condition hc       ON f.house_condition_id = hc.house_condition_id
    GROUP BY r.region_name;
""")
print("Шаг 4: marts_by_region построена")

# ===== ШАГ 5. Витрина marts_by_management =====
cur.execute("""
    DROP TABLE IF EXISTS marts_by_management;
    CREATE TABLE marts_by_management AS
    SELECT
        mo.management_organization_name,
        COUNT(*) AS house_count,
        SUM(f.total_area) AS total_area,
        AVG(f.deterioration) AS avg_deterioration,
        AVG(CASE WHEN f.deterioration > 70 THEN 1 ELSE 0 END) AS share_high_wear,
        AVG(CASE WHEN hc.house_condition = 'Аварийный' THEN 1 ELSE 0 END) AS share_accident
    FROM fact_houses f
    LEFT JOIN dim_management_organization mo ON f.management_organization_id = mo.management_organization_id
    LEFT JOIN dim_house_condition hc          ON f.house_condition_id = hc.house_condition_id
    GROUP BY mo.management_organization_name
    ORDER BY house_count DESC;
""")
print("Шаг 5: marts_by_management построена")

# ===== ШАГ 6. Витрина marts_by_energy_class =====
cur.execute("""
    DROP TABLE IF EXISTS marts_by_energy_class;
    CREATE TABLE marts_by_energy_class AS
    SELECT
        ec.energy_class_code,
        ec.energy_class_group,
        COUNT(*) AS house_count,
        SUM(f.total_area) AS total_area,
        AVG(f.deterioration) AS avg_deterioration
    FROM fact_houses f
    LEFT JOIN dim_energy_efficency_class ec ON f.energy_class_id = ec.energy_class_id
    GROUP BY ec.energy_class_code, ec.energy_class_group
    ORDER BY house_count DESC;
""")
print("Шаг 6: marts_by_energy_class построена")

# ===== ЗАКРЫТИЕ =====
cur.close()
conn.close()
print("Все витрины построены.")
