# OSM 도로망 추출 — 맥 터미널 실행 안내

작성 2026-09-04 · 담당 김지훈

분석 환경(클라우드·로컬 VM)은 `overpass-api.de`, `geofabrik`, `openstreetmap.org` 가
모두 프록시에서 차단된다. **네트워크가 열린 본인 맥 터미널에서 한 번만 돌리면**
이후 파이프라인은 저장된 파일만 읽으므로 다시 네트워크가 필요 없다.

---

## 1. 준비 — 한 번만

터미널(응용 프로그램 → 유틸리티 → 터미널)을 열고 순서대로 붙여넣는다.

```bash
cd ~/Desktop/프로젝트/부산_공모전/busan-subsidence

python3 -m venv .venv-osm
source .venv-osm/bin/activate
pip install --upgrade pip
pip install osmnx geopandas networkx
```

가상환경을 따로 만드는 이유는 맥 시스템 파이썬을 건드리지 않기 위해서다.
`.venv-osm` 은 `.gitignore` 의 `data/` 와 별개이므로 커밋되지 않도록 확인한다.

설치가 끝나면 확인한다.

```bash
python3 -c "import osmnx, geopandas; print(osmnx.__version__, geopandas.__version__)"
```

---

## 2. 파일럿 먼저 — 3~5분

전역부터 걸지 않는다. 원도심 세 개 구로 먼저 돌려 파이프라인이 도는지 본다.

```bash
python3 src/osm_extract.py 중구 동구 서구
```

> zsh는 대화형 셸에서 `#`을 주석으로 보지 않는다. 명령 뒤에 설명을 붙여 통째로
> 붙여넣으면 그 글자가 구·군 이름으로 들어간다. 명령 줄만 붙여넣는다.
> (스크립트에 `#` 이후를 잘라내는 방어 코드를 넣어두긴 했다.)

끝나면 화면 마지막에 실측값이 표로 나온다. 이 출력이 정상이면 전역으로 넘어간다.

---

## 3. 전역 — 수십 분

```bash
python3 src/osm_extract.py
```

부산 전역 보행 도로망이라 다운로드에 수십 분, 메모리 수 GB가 든다.
**맥이 잠들면 중단되므로** 실행 전에 시스템 설정에서 절전을 잠시 꺼두거나,
`caffeinate` 를 앞에 붙인다.

```bash
caffeinate python3 src/osm_extract.py
```

---

## 4. 끝난 뒤

`data/raw/` 에 아래 네 개가 생긴다. 별도로 옮길 필요 없다. 폴더가 세션에 연결돼 있어
그대로 이어서 처리된다.

```
osm_busan_walk_20260904.graphml     보행 도로망 원본 그래프
osm_busan_edges_20260904.gpkg       구간·노드 (EPSG:5187, 길이 포함)
osm_busan_steps_20260904.gpkg       계단 highway=steps
osm_busan_stats_20260904.json       엣지 수 · 구간 길이 분포 · 계단 수
```

마지막 파일이 **구간 2 분석 단위 확정 회의에 가져갈 실측값**이다.
화면에 찍힌 표를 그대로 카톡에 공유하면 회의 안건이 정리된다.

계단 개수는 하은님의 계단 커버리지 검증(표본 100개소 로드뷰 대조) 모수가 된다.

---

## 5. 막혔을 때

| 증상 | 조치 |
|---|---|
| `pip install geopandas` 가 오래 걸리거나 실패 | `pip install geopandas` 대신 `pip install osmnx` 만 해도 의존성으로 함께 깔린다 |
| 폴리곤 관련 Overpass 오류 | 전역 대신 구 단위로 나눠 여러 번 실행하고, 나중에 합친다 |
| 다운로드 중 멈춤 | Overpass 서버 혼잡이다. `Ctrl+C` 후 잠시 뒤 재실행하면 캐시가 남아 있어 이어진다 |
| 메모리 부족으로 강제 종료 | 구 단위 실행으로 전환한다 |

두 번 이상 같은 지점에서 막히면 그 화면을 그대로 공유한다.
스크립트를 고치는 편이 빠른 경우가 많다.
