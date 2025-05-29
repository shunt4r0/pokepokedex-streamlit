import streamlit as st
import pandas as pd
import requests
import json
import os
from st_aggrid import AgGrid, GridOptionsBuilder
from typing import List, Dict, Set, Tuple

# 画面カラー設定
st.markdown(
    '''
    <style>
    [data-testid="stAppViewContainer"] {background-color: rgb(242,242,242); color: #000000;}
    body, .stText, .markdown-text-container {color: #000000;}
    </style>
    ''', unsafe_allow_html=True
)

# 永続化用 JSON ファイル
MODE_FILE = 'mode_data.json'

def load_mode_data() -> Dict[str,str]:
    if os.path.exists(MODE_FILE):
        with open(MODE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_mode_data(data: Dict[str,str]):
    with open(MODE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

API = 'https://pokeapi.co/api/v2'

@st.cache_data
def fetch_species_list() -> List[Dict]:
    res = requests.get(f'{API}/pokemon-species?limit=386').json()
    species = []
    for i, entry in enumerate(res['results'], start=1):
        data = requests.get(entry['url']).json()
        ja = next((n['name'] for n in data['names'] if n['language']['name'] in ('ja','ja-Hrkt')), entry['name'])
        species.append({'id': i, 'name': ja, 'species_url': entry['url']})
    return species

@st.cache_data
def fetch_encounters(poke_id: int) -> List[Dict]:
    return requests.get(f'{API}/pokemon/{poke_id}/encounters').json()

@st.cache_data
def fetch_type(tp: str) -> Dict:
    return requests.get(f'{API}/type/{tp}').json()

@st.cache_data
def fetch_move(mv: str) -> Dict:
    return requests.get(f'{API}/move/{mv}').json()

@st.cache_data
def fetch_egg_group(name: str) -> Dict:
    return requests.get(f'{API}/egg-group/{name}').json()

GAME_COLUMNS: List[Tuple[str,str]] = [
    ('firered','FR'), ('leafgreen','LG'),
    ('ruby','R'), ('sapphire','S'), ('emerald','E'),
]

@st.cache_data
def fetch_location_area_jp(url: str) -> str:
    la = requests.get(url).json()
    jp = next((n['name'] for n in la['names'] if n['language']['name'] in ('ja','ja-Hrkt')), None)
    if jp: return jp
    loc = requests.get(la['location']['url']).json()
    return next((n['name'] for n in loc['names'] if n['language']['name'] in ('ja','ja-Hrkt')), la['name'])

# 進化チェーン用マッピング
from typing import Any

def build_evolution_maps(chain: Dict[str,Any]) -> Tuple[Dict[int,int], Dict[int,List[int]]]:
    parent_map, child_map = {}, {}
    def recurse(node: Dict[str,Any], parent_id: int = None):
        curr_id = int(node['species']['url'].rstrip('/').split('/')[-1])
        if parent_id: parent_map[curr_id] = parent_id
        child_ids = []
        for ev in node.get('evolves_to', []):
            cid = int(ev['species']['url'].rstrip('/').split('/')[-1])
            child_ids.append(cid)
            recurse(ev, curr_id)
        child_map[curr_id] = child_ids
    recurse(chain)
    return parent_map, child_map

# メイン画面
def main():
    st.title('第3世代ポケモン入手可否一覧')
    # モード永続データ
    mode_data = load_mode_data()

    selected_games = st.multiselect(
        'ゲームタイトルで絞り込み', [lbl for _,lbl in GAME_COLUMNS], default=[]
    )

    species = fetch_species_list()
    id_to_jp = {s['id']: s['name'] for s in species}

    rows = []
    for s in species:
        enc = fetch_encounters(s['id'])
        versions = {vd['version']['name'] for e in enc for vd in e['version_details']}
        row = {'No': s['id'], '名前': s['name'], 'モード': mode_data.get(str(s['id']), '')}
        for key,label in GAME_COLUMNS:
            row[label] = '〇' if key in versions else ''
        rows.append(row)
    df = pd.DataFrame(rows)
    if selected_games:
        df = df[df[selected_games].any(axis=1)]
    # 列順
    df = df[['No','名前','モード'] + [lbl for _,lbl in GAME_COLUMNS]]

    gb = GridOptionsBuilder.from_dataframe(df)
    for col in ['S','E']:
        gb.configure_column(col, width=70)
    gb.configure_column('モード', editable=True,
                        cellEditor='agSelectCellEditor',
                        cellEditorParams={'values':['図鑑','ボックス','空白']})
    gb.configure_selection('single', use_checkbox=False)
    grid_resp = AgGrid(df, gridOptions=gb.build(), enable_enterprise_modules=False)

    # モード列更新を永続化
    updated = grid_resp.get('data')
    if updated is not None:
        new_modes = {str(int(r['No'])): r.get('モード','') for r in updated}
        save_mode_data(new_modes)

    selected = grid_resp.get('selected_rows', [])
    if selected:
        sel = selected[0]
        show_detail(int(sel['No']), sel['名前'], id_to_jp)

# 詳細画面
from typing import Any

def show_detail(poke_id: int, ja_name: str, id_to_jp: Dict[int,str]):
    st.header(f'{ja_name} (No.{poke_id}) の詳細')
    # (中略：詳細情報ロジックは同様)

if __name__ == '__main__':
    main()
