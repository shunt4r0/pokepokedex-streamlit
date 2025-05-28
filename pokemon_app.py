import streamlit as st
import pandas as pd
import requests
from st_aggrid import AgGrid, GridOptionsBuilder
from typing import List, Dict, Set, Tuple

# 画面カラー設定
st.markdown(
    '''
    <style>
    /* Streamlit メインビューコンテナの背景色と文字色を変更 */
    [data-testid="stAppViewContainer"] {
        background-color: rgb(242,242,242);
        color: #000000;
    }
    /* 本文テキストも確実に黒に設定 */
    body, .css-1d391kg, .stText, .markdown-text-container {
        color: #000000;
    }
    </style>
    ''',
    unsafe_allow_html=True
)

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
def fetch_pokemon_species(poke_id: int) -> Dict:
    return requests.get(f'{API}/pokemon-species/{poke_id}').json()

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


def build_evolution_maps(chain: Dict) -> Tuple[Dict[int,int], Dict[int,List[int]]]:
    parent_map, child_map = {}, {}
    def recurse(node: Dict, parent_id: int = None):
        curr_id = int(node['species']['url'].split('/')[-2])
        if parent_id: parent_map[curr_id] = parent_id
        child_ids = []
        for ev in node.get('evolves_to', []):
            cid = int(ev['species']['url'].split('/')[-2])
            child_ids.append(cid)
            recurse(ev, curr_id)
        child_map[curr_id] = child_ids
    recurse(chain)
    return parent_map, child_map


def main():
    st.title('第3世代ポケモン入手可否一覧')
    selected_games = st.multiselect(
        'ゲームタイトルで絞り込み',
        [label for _, label in GAME_COLUMNS], default=[]
    )

    species = fetch_species_list()
    id_to_jp = {s['id']: s['name'] for s in species}

    rows = []
    for s in species:
        enc = fetch_encounters(s['id'])
        versions = {vd['version']['name'] for e in enc for vd in e['version_details']}
        # 入手状況列を3列目に設定
        row = {'No': s['id'], '名前': s['name'], '入手状況': ''}
        for key, label in GAME_COLUMNS:
            row[label] = '〇' if key in versions else ''
        rows.append(row)
    df = pd.DataFrame(rows)
    # カラムの順序を No, 名前, 入手状況, ゲーム列 の順に指定
    column_order = ['No', '名前', '入手状況'] + [label for _, label in GAME_COLUMNS]
    df = df[column_order]
    if selected_games:
        df = df[df[selected_games].any(axis=1)]

    gb = GridOptionsBuilder.from_dataframe(df)
    for col in ['S','E']:
        gb.configure_column(col, width=70)
    # 入手状況列にプルダウン編集機能を追加
    gb.configure_column(
        '入手状況', editable=True,
        cellEditor='agSelectCellEditor',
        cellEditorParams={'values': ['図鑑','ボックス','']}
    )
    gb.configure_selection('single', use_checkbox=False)

    grid_resp = AgGrid(
        df, gridOptions=gb.build(), enable_enterprise_modules=False
    )
    selected = grid_resp['selected_rows']
    if len(selected) > 0:
        sel = selected.iloc[0] if hasattr(selected, 'iloc') else selected[0]
        show_detail(int(sel['No']), sel['名前'], id_to_jp)


def show_detail(poke_id: int, ja_name: str, id_to_jp: Dict[int,str]):
    st.header(f'{ja_name} (No.{poke_id}) の詳細')

    st.subheader('入手場所（出現確率）')
    enc = fetch_encounters(poke_id)
    loc_map = {label: [] for _,label in GAME_COLUMNS}
    for e in enc:
        area_jp = fetch_location_area_jp(e['location_area']['url'])
        for vd in e['version_details']:
            key = vd['version']['name']
            label = dict(GAME_COLUMNS).get(key)
            if not label: continue
            for det in vd.get('encounter_details', []):
                loc_map[label].append((area_jp, det.get('chance',0)))
    for label, entries in loc_map.items():
        st.markdown(f'**{label}**')
        for area, chance in sorted(entries, key=lambda x: x[1], reverse=True):
            st.write(f'- {area}（出現確率: {chance}%）')

    st.subheader('弱点（タイプ相性）')
    poke = requests.get(f'{API}/pokemon/{poke_id}').json()
    weak = set()
    for t in [t['type']['name'] for t in poke['types']]:
        for rel in fetch_type(t)['damage_relations']['double_damage_from']:
            weak.add(rel['name'])
    st.write(', '.join(
        next((n['name'] for n in fetch_type(w)['names'] if n['language']['name']=='ja'), w)
        for w in sorted(weak)
    ))

    st.subheader('第3世代 レベルアップ技')
    moves = [(vd['level_learned_at'], m['move']['name'])
             for m in poke['moves']
             for vd in m['version_group_details']
             if vd['move_learn_method']['name']=='level-up'
             and vd['version_group']['name'] in ['firered-leafgreen','ruby-sapphire','emerald']]
    for lvl, mv in sorted(set(moves)):
        md = fetch_move(mv)
        mv_jp = next((n['name'] for n in md['names'] if n['language']['name']=='ja'), mv)
        jp_type = next((n['name'] for n in fetch_type(md['type']['name'])['names'] if n['language']['name']=='ja'), md['type']['name'])
        st.write(f'Lv.{lvl}  {mv_jp} ({jp_type})')

    st.subheader('進化情報')
    sp = fetch_pokemon_species(poke_id)
    parent_map, child_map = build_evolution_maps(requests.get(sp['evolution_chain']['url']).json()['chain'])
    if parent_map.get(poke_id):
        pid = parent_map[poke_id]
        st.write(f'**進化元**: No.{pid} {id_to_jp.get(pid,pid)}')
    if child_map.get(poke_id):
        st.write('**進化先**: ' + ', '.join(
            f'No.{cid} {id_to_jp.get(cid,cid)}' for cid in child_map[poke_id]
        ))

    st.subheader('タマゴグループ')
    for g in sp.get('egg_groups', []):
        eg = fetch_egg_group(g['name'])
        ja_eg = next((n['name'] for n in eg['names'] if n['language']['name'] in ('ja','ja-Hrkt')), g['name'])
        st.write(f'- {ja_eg}')

    st.subheader('たまご技')
    egg_moves = {m['move']['name'] for m in poke['moves']
                 for vd in m['version_group_details']
                 if vd['move_learn_method']['name']=='egg'
                 and vd['version_group']['name'] in ['firered-leafgreen','ruby-sapphire','emerald']}
    for mv in sorted(egg_moves):
        md = fetch_move(mv)
        mv_jp = next((n['name'] for n in md['names'] if n['language']['name']=='ja'), mv)
        jp_type = next((n['name'] for n in fetch_type(md['type']['name'])['names'] if n['language']['name']=='ja'), md['type']['name'])
        st.write(f'- {mv_jp} ({jp_type})')

if __name__ == '__main__':
    main()