import pandas as pd
import psycopg2
from psycopg2 import sql
from datetime import datetime

# ======= НАСТРОЙКИ =======
DB_HOST = 'localhost'
DB_PORT = '5432'          
DB_NAME = 'gh_houses'
DB_USER = 'admin'
DB_PASS = 'admin'
MAX_AREA = 10000000  # 10 млн м²

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
conn.autocommit = False
cur = conn.cursor()

# ======= 1. Читаем из stg_houses (НЕ трогаем её) =======
print('Читаю stg_houses...')
df = pd.read_sql('SELECT * FROM stg_houses', conn, dtype=str)
print('Строк в stg_houses:', len(df))

# ======= 2. Очищаем факт и измерения =======
trunc_tables = [
    'fact_houses',
    'dim_region', 'dim_municipality',
    'dim_house_type', 'dim_house_condition', 'dim_internal_walls_type',
    'dim_energy_efficency_class', 'dim_house_management_type',
    'dim_life_cycle_stage', 'dim_management_organization', 'dim_date'
]
cur.execute('TRUNCATE TABLE ' + ', '.join(trunc_tables) + ' CASCADE')
conn.commit()
print('Очищены: факт + все измерения')

# ======= 3. Вспомогательные функции =======
def to_date(val):
    if pd.isna(val) or str(val).strip() == '':
        return None
    s = str(val).strip()
    for fmt in ('%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def clean_year(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    try:
        y = int(float(s))
    except (ValueError, TypeError):
        return None
    return y if 1800 <= y <= 2100 else None

def clean_area(val):
    if pd.isna(val):
        return None
    try:
        a = float(val)
    except (ValueError, TypeError):
        return None
    if a < 0 or a > MAX_AREA or a == 0:
        return None
    return a

def to_int(val):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

def to_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def to_bool(val):
    if pd.isna(val):
        return False
    s = str(val).strip().lower()
    return s in ('1', 'true', 'yes', 'да', 'истина')

def clean_str(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s.lower() in ('nan', 'none', ''):
        return None
    return s

# ======= 4. dim_region =======
print('Строю dim_region...')
regions = df[['region_name', 'region_oktmo', 'region_okato']].dropna(subset=['region_oktmo']).drop_duplicates(subset=['region_oktmo'])
region_map = {}
for _, r in regions.iterrows():
    cur.execute("INSERT INTO dim_region (region_name, region_oktmo, region_okato) VALUES (%s, %s, %s) RETURNING region_id",
                (clean_str(r['region_name']), r['region_oktmo'], r['region_okato']))
    region_map[r['region_oktmo']] = cur.fetchone()[0]
conn.commit()
print('  Регионов:', len(region_map))

# ======= 5. dim_municipality =======
print('Строю dim_municipality...')
municip = df[['municipality_oktmo', 'municipality_okato', 'region_oktmo']].dropna(subset=['municipality_oktmo']).drop_duplicates(subset=['municipality_oktmo'])
municip_map = {}
for _, r in municip.iterrows():
    reg_id = region_map.get(r['region_oktmo'])
    cur.execute("INSERT INTO dim_municipality (municipality_name, municipality_oktmo, municipality_okato, region_id) VALUES (%s, %s, %s, %s) RETURNING municipality_id",
                (r['municipality_oktmo'], r['municipality_oktmo'], r['municipality_okato'], reg_id))
    municip_map[r['municipality_oktmo']] = cur.fetchone()[0]
conn.commit()
print('  Муниципалитетов:', len(municip_map))

# ======= 6. Простые измерения =======
def load_simple_dim(table, col_csv, col_db, pk):
    vals = df[col_csv].dropna().unique()
    id_map = {}
    for v in vals:
        cur.execute(sql.SQL("INSERT INTO {} ({}) VALUES (%s) RETURNING {}").format(
            sql.Identifier(table), sql.Identifier(col_db), sql.Identifier(pk)), (v,))
        id_map[v] = cur.fetchone()[0]
    return id_map

print('Строю простые измерения...')
house_type_map = load_simple_dim('dim_house_type', 'house_type', 'house_type', 'house_type_id')
condition_map  = load_simple_dim('dim_house_condition', 'condition', 'house_condition', 'house_condition_id')
walls_map      = load_simple_dim('dim_internal_walls_type', 'internal_walls_type', 'internal_walls_type', 'walls_type_id')
mng_type_map   = load_simple_dim('dim_house_management_type', 'house_management_type', 'management_type', 'management_type_id')
lifecycle_map  = load_simple_dim('dim_life_cycle_stage', 'life_cycle_stage', 'life_cycle_stage', 'life_cycle_stage_id')

# ======= 7. dim_energy_efficency_class (split code / group) =======
print('Строю dim_energy_efficency_class...')
energy_map = {}
for v in df['energy_efficency_class'].dropna().unique():
    v = str(v).strip()
    if '(' in v and v.endswith(')'):
        code = v[:v.index('(')].strip()
        group = v[v.index('(')+1:-1].strip()
    elif '(' in v:
        code = v[:v.index('(')].strip()
        group = v[v.index('(')+1:].strip()
    else:
        code = v
        group = None
    cur.execute("INSERT INTO dim_energy_efficency_class (energy_class_code, energy_class_group) VALUES (%s, %s) RETURNING energy_class_id",
                (code, group))
    energy_map[v] = cur.fetchone()[0]
conn.commit()

# ======= 8. dim_management_organization =======
print('Строю dim_management_organization...')
org = df[['management_organization_name', 'management_organization_link']].dropna(subset=['management_organization_name']).drop_duplicates(subset=['management_organization_name'])
org_map = {}
for _, r in org.iterrows():
    cur.execute("INSERT INTO dim_management_organization (management_organization_name, management_organization_link) VALUES (%s, %s) RETURNING management_organization_id",
                (clean_str(r['management_organization_name']), clean_str(r['management_organization_link'])))
    org_map[r['management_organization_name']] = cur.fetchone()[0]
conn.commit()
print('  Организаций:', len(org_map))

# ======= 9. dim_date =======
print('Строю dim_date...')
dates = df['deterioration_estimation_date'].dropna().apply(to_date).dropna().unique()
date_map = {}
for d in dates:
    cur.execute("INSERT INTO dim_date (date, year, quarter, month, month_name, day, weekday, is_weekend_flg) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (date) DO NOTHING RETURNING date_id",
                (d, d.year, (d.month - 1) // 3 + 1, d.month, d.strftime('%B'), d.day, d.weekday() + 1, d.weekday() >= 5))
    row = cur.fetchone()
    if row is None:
        cur.execute("SELECT date_id FROM dim_date WHERE date=%s", (d,))
        row = cur.fetchone()
    date_map[d] = row[0]
conn.commit()
print('  Дат:', len(date_map))

print('Измерения построены.')

# ======= 10. fact_houses =======
print('Строю fact_houses...')
rows_to_insert = []
for _, r in df.iterrows():
    gis_id = clean_str(r.get('gisgkh_guid'))
    if not gis_id:
        continue
    wear_date = to_date(r.get('deterioration_estimation_date'))
    fias_id = clean_str(r.get('fias_id'))
    if not fias_id:
        fias_id = ''
    rows_to_insert.append((
        gis_id,
        fias_id,
        clean_str(r.get('cadastral_number')),
        date_map.get(wear_date),
        to_float(r.get('deterioration')),
        condition_map.get(r.get('condition')),
        region_map.get(r.get('region_oktmo')),
        municip_map.get(r.get('municipality_oktmo')),
        clean_str(r.get('postal_code')),
        to_float(r.get('latitude')),
        to_float(r.get('longitude')),
        to_int(r.get('flats')),
        clean_area(r.get('total_area')),
        clean_area(r.get('residental_premises_area')),
        clean_str(r.get('plan_series')),
        clean_year(r.get('building_year')),
        to_int(r.get('comissioning_year')),
        to_int(r.get('reconstruction_year')),
        house_type_map.get(r.get('house_type')),
        walls_map.get(r.get('internal_walls_type')),
        energy_map.get(r.get('energy_efficency_class')),
        mng_type_map.get(r.get('house_management_type')),
        org_map.get(r.get('management_organization_name')),
        to_bool(r.get('regional_property')),
        to_bool(r.get('municipal_property')),
        clean_str(r.get('full_address')),
        lifecycle_map.get(r.get('life_cycle_stage')),
    ))

insert_sql = """
INSERT INTO fact_houses (
    gisghk_id, fias_id, cadastral_number, date_id, deterioration,
    house_condition_id, region_id, municipality_id, postal_code,
    latitude, longitude, flats, total_area, residental_premises_area,
    plan_series, building_year, comissioning_year, reconstruction_year,
    house_type_id, walls_type_id, energy_class_id, management_type_id,
    management_organization_id, regional_property_flg, municipal_property_flg, full_address,
    life_cycle_stage_id
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s
) ON CONFLICT (gisghk_id) DO NOTHING
"""

batch = 5000
for i in range(0, len(rows_to_insert), batch):
    cur.executemany(insert_sql, rows_to_insert[i:i + batch])
    conn.commit()
    print(f'Fact загружен: {min(i + batch, len(rows_to_insert))} / {len(rows_to_insert)}')

conn.commit()
print('Готово! Все данные перезалиты.')

cur.close()
conn.close()
