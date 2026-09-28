# Mealboard 보완 제안서 — 「2026 공공 AI 대전환 챌린지」(세션 1 자유주제) 출품 대비

> 작성 2026-09-28. 학생 프로젝트로 시작한 Mealboard 를 **성인 공무원 심사 기준**(필요성 20 · 창의성 30 · 활용성 20 · 완성도 15 · 확산가능성 15)에 맞춰 보완하기 위해, 세 관점의 리서치 에이전트(ML/데이터 · UI/UX · 급식·환경 도메인)가 각각 웹 조사(관점당 30~40회 검색, 원문 확인 20여 건)와 코드 검토를 수행한 결과를 종합했다. 일정: 수요조사 10-16 → 본 제출 11-11 → 예선 11-13~17 → 결선 11-26.
> 이 문서는 '무엇을 왜' 까지만 담는다. 채택된 항목은 PLAN 형식의 작업 계획으로 옮겨 구현한다(§4 로드맵이 그 초안).

---

## 0. 한 장 요약

**결론: 출품 적합. 세 관점이 공통으로 가리키는 보강 축은 셋이다.**

1. **정확도를 스스로 증명하는 시스템으로** — 지금은 자동 실측(체류시간)이 0건이라 "추정치"라는 말에 근거가 없다. 원인은 코드에서 확인됐고(§1.1), 개별 추적에 기대지 않는 **FIFO 누적곡선 추정기**로 바꾸면 매 창 실측이 성립한다. 여기에 표준 실측 프로토콜·오차 지표·측정 신뢰도 공개를 붙인다. → 완성도·창의성
2. **'학생 편의'에서 '급식 운영 도구'로 프레임 격상** — 필요성 근거를 "대기 안내"가 아니라 **"착석 식사시간 보장"**(AAP·CDC 20분, JAMA RCT)으로 옮기고, 영양교사·급식 운영진용 주간 리포트(학교급식법 시행령 13조 운영평가 항목 순서), 잔반 총량·식수 대조, 2027 영양기준 개정 프리셋, 탄소 계수 재설계를 더한다. → 필요성·활용성
3. **확산 패키지** — 전국 학교 92%가 식당 배식이고 급식실 대기 안내 서비스는 초·중·고에 **국내 사례가 없다**. 이식 패키지(설정 3파일 · 보정 수용 검사 · **개인정보보호법 §25 절차 서식**)와 공공 표준 어휘(서울시 4단계) 정렬, 키오스크 모드로 "다른 학교가 그대로 채택"할 수 있게 한다. → 확산가능성·활용성

**11-11 전 필수 10건(§3 P1~P10)** 을 6주에 배치했다(§4). ML 예보 모델은 **넣지 않는다**(§5) — 소표본에서 나이브를 못 이기며, 평가·구간·나우캐스트가 완성도를 더 올린다.

---

## 1. 현재 상태 진단 (코드·데이터로 확인된 사실)

### 1.1 자동 실측(체류시간) 이벤트가 0건인 이유 — 코드 확인
- `vision/counting.py` `DwellTracker.forget(alive)` 와 `LineCounter.forget(alive)` 가 **현재 프레임에 검출된 ID 집합 밖의 기록을 즉시 삭제**한다. ByteTrack 은 매칭 실패 트랙을 `track_buffer`(기본 30 **프레임** = 3 fps 에서 10초) 동안 내부에 보관하지만 결과 `boxes.id` 에는 내보내지 않으므로, **한 프레임(0.33초)만 가려져도 진입 시각이 지워지고** 같은 ID 로 복귀하면 진입이 새로 찍힌다 → 체류가 마지막 연속 구간만 남아 `MIN_DWELL_SEC=20` 에 걸려 폐기. `observe()` 주석("깜빡임으로 잠깐 나가도 리셋하지 않는다")과 실제 동작이 어긋난다.
- 같은 경로로 `LineCounter.side` 도 지워져 가림 직후 통과가 안 세어질 수 있다(λ 과소). 반대로 `served` 는 출구 방향(+1)만 누적하고 복귀(−1)를 빼지 않아 λ선 앞 왕복이 이중 카운트된다(λ 과대 → W 과소). 두 효과의 크기는 표본에 `reappear_n`·`new_id_n` 을 남겨 하루 보면 판명된다.
- 구조적 한계: 실측 중앙값 1~2.5분 = 3 fps 에서 **180~450 프레임 연속 ID 유지**를 요구한다. 밀집 줄에서는 어떤 트래커로도 어렵다(FraMOT·APPTracker: 저 fps 에서 최신 트래커 전부 급락).

### 1.2 Little's law 의 알려진 편향
- Kim & Whitt(2013): 도착률이 시간에 따라 변하고 서비스가 길면 간접 추정기 L/λ 는 유의하게 편향 — 급식 창 개시 15분(줄은 느는데 λ 는 낮음)의 과대추정과 같은 상황. 시간가변 Little's law 또는 누적곡선(Newell) 추정이 해법.

### 1.3 화면·접근성에서 확인된 미달 항목(계산값, 도구 재확인 권장)
- 각주 색 `--ink3 #9A958A` 는 카드 바탕 대비 약 2.9:1(AA 4.5:1 미달), 혼잡 히어로 보조 라벨 약 3.2:1, 히트맵 셀 22px(WCAG 2.2 목표 크기 24px 미달), `manifest.json` 512 아이콘·description·screenshots 없음(설치 배너 조건 미충족 추정). 좋은 점: reduced-motion 존중, 색+문장+칩 병기, `role=status`.

### 1.4 도메인 지표의 약점
- `carbon_std.json` 은 FAO 2013 전 지구 단일 계수(2.5 kgCO₂e/kg)라 쇠고기와 채소가 같은 값 — 심사 예상 질문 "계수 출처가 뭔가요?" 에 취약. 국내 공인 계수는 곡류·과일·채소 61종뿐이고 육류 공인 계수가 없다.
- 영양 기준은 현행 별표3(2021)과 일치하지만 **2027-03-01 시행 개정**(2025 KDRIs: 탄수 50~65 / 단백 10~20 / 지방 15~30)이 예고돼 있다. MAR 은 '제공 영양' 기준(섭취 아님)이며 NEIS 미량영양소 6종만 분모라는 한계가 각주에 없다. `upper_factor 1.5` 는 문헌 근거 없는 자체값.

### 1.5 법적 위치 — 강점이자 절차
- 개인정보 보호법 **§25①6 + 시행령 §22①1**("출입자 수 등 통계값 산출을 위해 영상정보를 일시적으로 처리·미저장")이 이 설계에 직접 대응한다 — '프레임 미저장·숫자만' 은 선의가 아니라 **법정 예외 요건 그 자체**. 단 안내판(§25④)·임의조작 금지(§25⑤)·운영관리방침(§25⑦)·학교운영위원회 심의 또는 설명회·설문 등 사전 의견수렴은 그대로 필요하다. 관리자 실사 MJPEG(≤10분·미저장·감사)은 '설정·보정 목적 실시간 열람'으로 운영방침에 한정 명문화. **시행령 조문은 검색 요약 기반이므로 국가법령정보센터 원문 대조 후 인용**(§6).
- 2026-09-11 시행 학교 CCTV 의무화(출입문·복도·계단)와는 **목적을 분리**한다 — Mealboard 카메라는 보안 CCTV 가 아니라 '통계 센서'. 저장소·계정 혼용 금지, 조리 종사자 작업 구역이 화각에 들어가지 않게(ROI 밖은 아예 계수하지 않음을 설명).

---

## 2. 관점별 핵심 발견 (근거 요약 · 출처는 §7)

### 2.1 데이터·ML
- **상용·공공 시스템의 공통 설계 = 입·출구 계수 + 영상 미저장 + 센서 안 처리**(Xovis 공항, Canon 큐 모델 특허 2건, 현대그린푸드 'AI 피플카운팅' 2025-02, 삼성웰스토리 2026-05, Telraam, OpenDataCam). Canon 특허 US11645895B2 는 개별 추적 없이 **유입 = 줄 인원 변화 + 이탈 수**(인원 보존)로 대기시간을 낸다 — Mealboard 가 이미 가진 L 과 통과 이벤트만으로 가능.
- **학교 급식실 카메라 대기시간 사례는 국내외 공개 자료에 없음** → 창의성 근거. 대학은 예약·번호표('야미'), 미국 대학은 Wi‑Fi/BT 점유율(Occuspace/Waitz).
- **에지 fps**: Hailo‑10H 모델 주 yolov8n 375 fps·yolov11n 302 fps(640). Ultralytics 공식 Hailo 내보내기는 10H 지원(x86_64 컴파일), `track` 지원은 문서 미명시 → 정식 HEF + HailoRT + `ultralytics.trackers.BYTETracker/BOTSORT` 직접 공급이 안전 경로. 남는 예산으로 2×2 타일 추론 시 먼 줄 꼬리 recall 개선(추정).
- **예보 ML**: M5·'Mind the naive forecast'(2025) — 소표본·저예측성 시계열에서 어떤 모델도 나이브를 일관되게 못 이김. 현행 예보(같은 요일 4주 평균×메뉴 계수)는 사실상 계절 나이브 + 보정이며 11-11 까지 약 100 창‑일은 GBM 검증량이 아니다. 국내 선례(LH×데이콘 식수 예측 2021, 대학 식당 RF MAE 4.8%)는 **메뉴 텍스트·달력 효과·날씨**가 주요 특성임을 보여 준다 — 지금은 특성을 **축적**할 때.
- **검증 프로토콜**(상용 피플카운터 관행): 관측자 2인 독립, 한산+피크 4시간 창을 15분 버킷, **방향별** 정확도(순계수는 과대·과소 상쇄로 부풀려짐), 범위로 보고. MAPE 는 0 근처 대기 때문에 금지.

### 2.2 UI/UX
- **불확실성은 '숨기지 말고 단순하게'**: Google 인기 시간대(데이터 부족하면 미표시 + 'Live' 배지 + 상대 표현), 멜버른 응급실 대기표시 연구(불확실성 그래프는 이용자를 "압도" → 단순 문장·범위), 버스 도착 연구(빈도 표현 "5번 중 4번은 3분 안"이 직관적), Allon 2011("곧" 같은 모호한 약속의 합리성), RCT("기대보다 짧게 끝날 때 만족" → 보수적 판정 유지).
- **정보 공개의 분산 효과와 헤딩(herding) 역효과가 실증됨**: 홍콩 응급실 시뮬레이션(정확한 예측·5분 갱신이면 평균 대기 −29%, **부정확하면 +96%**), 오하이오주립대(낡은 정보 → 가장 짧아 보이는 줄로 몰림), 바르샤바 버스(혼잡 정보로 30~70%가 다음 차 대기). → 추천 시각은 학급/학년별 오프셋·범위로, 갱신 5분 이내, 부정확할 땐 미표시, 디즈니식 부풀리기 금지.
- **공공 표준 어휘**: 서울시 실시간 도시데이터 4단계(여유·보통·약간 붐빔·붐빔, 5분 갱신, 면책 문구), 지하철 칸별 4색+뜻 문장. KRDS(범정부 디자인시스템) 본문 17px·행간 150%·고대비 모드, KWCAG 2.2.
- **키오스크**: 가독 거리 '글자 높이 1인치당 10피트', 학교 사이니지 3×5 룰(3줄×5단어), 대비 4.5:1. 국내 학교 급식실에 대기시간을 띄우는 사례 없음(공백).
- **잔반 집단 게이미피케이션**: 스웨덴 학급 대항 + 급식실 벽 게시 −35%, FIT Game 과일 +66%, 교육부 '행복한 교육' 주 단위 잔반 그래프 게시 권장, 서울시 '잔반제로 학교 대항전'(2025). 개인 랭킹은 금지(낙인).
- **PWA/알림**: iOS 웹 푸시는 홈 화면 설치본만, 2026-03 시행 수업 중 스마트기기 사용 금지법 → 알림은 옵트인·급식 창 안 1일 1회 상한. 설치 UI 는 512 아이콘·description·screenshots 로 즉시 개선 가능.

### 2.3 급식·환경 도메인·정책
- **필요성**: 전국 학교의 92%가 식당 배식(교실 배식 7.9%), 식당은 좌석 회전 1.7~2.5회전 전제 설계 → 시차 배식과 줄이 구조적. 경기 초등 학년별 급식 시각 격차 최대 90분. **착석 20분 미만이면 과일·채소 섭취↓·잔반↑**(JAMA Netw Open 2021 RCT), AAP·CDC 착석 20분 권고, 점심 20→25분 연장 시 잔반 −13%. 경기도 급식 잔반 6.1만 톤·처리비 100억+/년. 1일 급식 인원 538만 명(모수).
- **정책 타이밍**: 2026 학교급식 기본방향(자율선택급식·저탄소 급식의 날·영양상담 강화·알레르기 대체식단), 영양관리기준 개정 2027-03-01 시행, 학교장 급식 만족도 조사 연 1회 의무, 시행령 13조 운영평가(위생·영양·경영·식생활 지도·**수요자 만족도**) — Mealboard 데이터가 운영평가 항목에 직접 대응. 영양교사 직무수행도가 가장 낮은 영역이 영양상담·교육 → "데이터가 상담 시간을 돌려준다".
- **차별화**: 상용(현대그린푸드·삼성웰스토리)은 기업 구내식당, 잔반 AI(누비랩)는 개인 식판 촬영 — Mealboard 는 초·중·고 무사례·오픈소스·Pi 1대·프레임 미저장·NEIS 연계 영양·탄소·알레르기 통합·학생 개발. 2025 챌린지 수상작(인천공항 운영효율, 식약처 위험예측, 창원시 물량 예측)은 **예측·행정효율·실증 수치**를 높게 본 신호.
- **탄소 계수**: 기후솔루션 2026-04 LCA(국내산 쇠고기 58.15, 닭고기 5.36 kgCO₂e/kg), 농진청 농산물 계수, 기후변화행동연구소 사례(한 끼 급식 0.59~0.79 kgCO₂e). 절대치보다 **상대 비교**(오늘 vs 주 평균, 저탄소 급식의 날 효과)로.
- **확산 병목은 기술이 아니라 절차**: 학교 CCTV 표준 가이드라인(학운위 심의 또는 설명회·설문, 안내판, 운영관리방침, 영향평가), 교육청 시범사업 경로(부산 조리로봇 국비, 경기 AI 푸드스캐너 희망교), 성지고 '예비식 기부' 의 데이터 표준화→규제혁신→192교 확산 모델.

---

## 3. 통합 제안 목록 (우선순위순 · 중복 합침)

표기: [지표] 기여 평가지표 · [난이도] 상/중/하 · [11-11] 마감 전 가능 여부 · [관점] 제안 출처

### A. 정확도·데이터 파이프라인 (완성도 15 · 창의성 30)

**P1. FIFO 누적곡선 대기시간 추정기 `W_fifo` — B안(체류 이벤트) 대체** [완성도·창의성] [중] [가능] [ML]
- 10초 표본마다 순통과 수 `d_t`(out−in) → 누적 출발 `D(t)`, 누적 도착 `A(t)=max(A(t−1), D(t)+L_t)`(인원 보존·단조화). 지금 통과한 사람의 대기 = `t − min{s: A(s) ≥ D(t)}`. 15분 창 중앙값을 `measured_wait_min` 자리에 넣으면 기존 하한·K 파이프라인이 최소 변경으로 살아난다. `samples` 에 `served_n` 열 추가(ALTER) → rollup 이 지난 날도 재계산.
- 순수 함수 + 합성 큐(포아송 도착·결정적 서비스) 단위검사, ID 를 뒤섞어도 결과 불변 검사. 오차원은 L 편향(화각 밖 꼬리)과 FIFO 위반(합류) — 후자는 중앙값이 흡수(추정).
- 근거: Newell 누적곡선, Canon US11645895B2, Kim & Whitt TVLL, arXiv 2106.00888.

**P2. 트랙 기억 유예 + 순유입 λ + 재출현 진단 지표** [완성도] [하] [가능(며칠)] [ML]
- `DwellTracker`·`LineCounter` 에 `last_seen[tid]` 를 두고 GRACE(≈15초 ≥ track_buffer/fps + 여유) 뒤에만 forget. `served` 는 `+c` 합산(복귀 −1 반영, 창 단위 0 하한)으로 왕복 이중 카운트 제거. 표본에 `reappear_n`·`new_id_n`(숫자) 기록 → 끊김 진단.
- `track_buffer` 만 키우지 말 것(좀비 트랙이 L 을 부풀림) — 유예는 계수기 쪽에서.

**P3. 표준 실측 프로토콜 + `ground_truth` 표 + `/api/insight/quality` 확장** [완성도·필요성] [하~중] [가능] [ML·도메인]
- 표 `(date, meal, kind[L|lambda|W], ts_start, ts_end, value, observer, method, note)` — 숫자만. 관리 앱 폼/CSV.
- 프로토콜: 관측자 2인 독립, 주 1회 이상·두 창, 한산+피크 포함, W 랩 ≥5, L 은 60초마다 10분 점검, λ 는 5분 통과 수(방향별). 지표: MAE(분)·부호 편향·±1분 적중률·**여유/보통/혼잡 3단계 혼동행렬**·P25–P75 커버리지. 급식일지 식수(영양교사가 NEIS 에 이미 기록)와 `served_est` 일 1회 대조. **MAPE 금지, 단일 숫자 발표 금지**(방향별·버킷별 범위로).

**P4. 측정 신뢰도 3단계 공개 + 카메라 이동·드리프트 감지** [완성도·확산] [중] [부분 가능] [ML·UI]
- 히어로에 신뢰도(커버리지·insufficient·camera_moved·reappear 비율 합성) 3단계 + 사유 문구, 서울시식 면책 한 줄. 창이 열릴 때 프레임 1장(메모리)의 ORB 특징점을 **보정 시점에 저장한 정적 배경 특징점(숫자)**과 호모그래피 잔차 비교 → 임계 초과 시 관리자 알림·`camera_moved` 플래그(참조는 정상 프레임으로만 갱신). 일 단위 `typical_rate`·평균 L 이 최근 4주 P10/P90 밖이면 드리프트 플래그.

**P5. 예보는 모델 교체 대신 평가·구간·나우캐스트·수축·특성 축적** [완성도·활용성] [하~중] [가능] [ML]
- (a) rollup 롤링 백테스트: 현행 vs 어제 같은 창 vs 전체 평균의 주간 MAE·스킬 점수 → `forecast_eval` 표 + 화면 각주. (b) 점 예보 대신 같은 요일 빈의 **P25–P75 구간**, 그 요일 ≥3일일 때만 게시(Google 규칙). (c) 창 안 **나우캐스트**: 최근 15분 실황/평소 비율(0.5~2 클램프)로 남은 곡선 스케일, 5분 갱신. (d) 메뉴 계수 **수축** `f=(n·f̂+k)/(n+k)`, k≈3. (e) `calendar_days` 표에 학사일정·공휴일 전후·기상청 강수/기온 적재 → 한 학기 뒤 GBM 교차학습 실험 재료.

**P6. 검출을 Hailo‑10H 로 옮겨 fps 3→15+ (저 fps 근본 원인 제거)** [완성도·활용성] [중~상] [가능(2~3주, 창 밖 시험)] [ML]
- 경로 B(안전): 모델 주 정식 HEF(COCO person) + HailoRT + `ultralytics.trackers` 클래스에 검출 직접 공급. 이후 MOT17 을 3/15 fps 로 서브샘플한 PC 실험(P6‑b)으로 `bytetrack` vs `botsort(gmc none, with_reid True, model auto)`·`track_buffer`·`match_thresh` 를 IDF1/ID 스위치로 비교해 권장값을 `.env` 로. ReID 임베딩은 프로세스 메모리에만(§2 원칙·시행령 §22 요건 동시 충족). HAT 는 뉴스·리포트 타이머(05:45·06:10·14:20)와 시간이 겹치지 않는다.
- 결선 전 완료가 안 되면 "진행 중 + 예비 실험 수치" 로 발표.

### B. 화면·UX (활용성 20 · 완성도 15)

**P7. 히어로 '불확실성 한 줄' + 상태별 대체 정보** [완성도·필요성] [하] [가능] [UI]
- 큰 숫자 앞 '약', 옆에 `오늘 범위 a~b분`(기존 `wait_range`)·상대 갱신 시각("30초 전")을 한 줄로. 선택: "지금 줄 서면 10번 중 8번은 3분 안"(최근 30분 분포). 데이터 없음·창 밖·'측정 준비 중' 에는 빈 히어로 대신 **"평소 이 시각 약 N분 · 다음 창 12:30 · 첫 10분이 가장 한산"** 같은 행동 가능한 문장 + 마지막 관측 시각. '측정 준비 중' 사유를 학생 언어로.
- 재검토 권고(사용자 승인 사항): 1분 미만 "37초" 표기는 정밀도 착시 — "1분 미만" 또는 30초 단위 반올림이 신뢰에 유리(Allon 2011, 멜버른 RITE).

**P8. 판정 어휘·색을 공공 표준과 정렬 + 접근성 패스** [확산·완성도] [하] [가능] [UI]
- 3단계 → 서울시 4단계 어휘(여유·보통·약간 붐빔·붐빔) 또는 최소한 각 단계에 지하철식 뜻 문장("바로 배식", "5분 안", "잠시 후 추천") 고정, 실시간뷰 구역 칩·밀집도 타일에도 같은 어휘. 색은 브랜드 3색 유지, 색+문장+아이콘 병기.
- 접근성: `.note`·`.eyebrow`·히트맵 각주 → `--ink2`(≈5.3:1)·12~13px, 혼잡 히어로 보조 라벨 불투명도 .62→.8+, 히트맵 셀 ≥24px(모바일은 열 12 또는 2행), 페이지 안 '움직임 줄이기'·'큰 글자' 토글(KRDS 17px/150%), 색약 시뮬레이터로 Sunsetdark·RdBu·요일 5색 확인 후 매뉴얼에 기록.

**P9. 키오스크(TV) 모드 `#tv`** [활용성·확산] [중] [가능] [UI]
- 급식실 입구·복도 1920×1080 전용: 상태색 전면 배경 + 판정 문장(3×5 룰) + 큰 숫자(6 m 가독 기준 헤드라인 120~160px) + 도착 예상 시각 + 접속 QR 상시, 12~15초 간격으로 '대기 → 평면도 밀집도 → 오늘 메뉴·알레르기(→ 잔반 목표 그래프)' 순환, 커서 숨김·SW 갱신 시 자동 재로드. 학교 TV 브라우저 전체화면만으로 동작. **실사·마커 영상 송출 금지**(§2) — 평면도·숫자만. 폰 제한 시간·폰 없는 학생에게도 정보 도달.

**P10. 영양교사·급식 운영진 '주간 리포트' 화면(읽기 전용·인쇄 1장·PDF)** [활용성·필요성·확산] [중] [MVP 가능] [UI·도메인]
- `insights.db`·`reports.db` 만으로: 시행령 13조 운영평가 순서(영양관리·식생활 지도·만족도·예산)로 시간대별 식수·병목 상위 3·λ 추이·메뉴별 대기(보정 계수순)·주간 영양기준 달성률(신·구 기준)·알레르기 노출 메뉴·저탄소 급식의 날 효과·측정 품질·'지난주 대비' 한 줄 해설(규칙 템플릿/로컬 LLM)·변경 노트(`CALC_VERSION`). 학교급식위원회·학운위 자료용. 관리 앱(8101) 뒤 또는 공개 `#report`. **해설 없는 대시보드 금지**(영국 Analysis Function 지침).

**P11. 분산 추천 넛지 카드(헤딩 방지 설계 내장)** [창의성·필요성] [중] [기본형 가능] [UI]
- 예보 곡선으로 "지금 / 5분 뒤 / 10분 뒤 예상" 3칩, 추천 출발 시각은 **학급(학년) 코드별 2~3분 오프셋**(localStorage 학급 선택) + 범위("12:35~12:40"), 5분 갱신 + 갱신 시각 노출. 관리자 화면에 '추천 시각대 대기 vs 비추천 시각대' 자동 대조 한 줄 → 결선 발표에서 "정보 공개→분산" 을 데이터로 증명. 판정 임계에 히스테리시스.

**P12. '이 숫자는 어떻게 나오나' 투명성 시트 + PWA 설치 정비 + 공개 위젯** [완성도·확산] [하] [가능] [UI]
- 각주 '추정치' 클릭 → 1장(카메라는 숫자만·W=L/λ 그림·실측 보정·오차 큰 순간·창 시간표·법적 근거 요약). `manifest.json` 512 아이콘·description·screenshots, 비침습 설치 배너(거절 기억, iOS 는 공유→홈 화면 안내). `/embed` 미니 카드(200×80)로 학교 홈페이지·학급 알림장 삽입. 푸시는 "대기 3분 이하면 알림" 옵트인(이중 허가·창 안 1일 1회·학급 오프셋) — 서버(pywebpush/VAPID)가 필요하므로 11-11 전에는 설치 UI 까지만.

### C. 도메인·정책 (필요성 20 · 확산가능성 15)

**P13. 필요성 프레임 전환: '착석 식사시간' 지표** [필요성↑↑·활용성] [하] [가능] [도메인]
- 히어로에 "지금 출발하면 착석 약 N분 확보"(창 종료 − 도착 예상 − 대기), 20분 미만이면 강조. 발표·신청서의 문제 정의를 "대기 안내"가 아니라 **"식사시간 보장(AAP·CDC 20분, JAMA RCT)"** 으로. 경기 초등 90분 격차·잔반 100억 원 수치를 필요성 절에.

**P14. 영양 기준 프리셋(2021 현행 / 2027 개정·2025 KDRIs) + 표기 정정** [완성도·확산] [하] [가능] [도메인]
- `nutrition_std.json` 에 `standard_version`·시행일 두 세트, 화면 토글 "2027.3 시행 기준 미리보기". 에너지 적정비율 50~65/10~20/15~30. UL 은 자체 배수(1.5) 대신 KDRIs UL 값. 화면 명칭을 '제공 영양 적정도' 로, NEIS 미량영양소 6종 한계를 각주에. 영양교사 검수 1시간.

**P15. 탄소 계수 재설계(식품군별 + 출처 각주 + 상대 비교)** [필요성(탄소중립 급식 정책 연계)·완성도] [중] [가능] [도메인]
- 단일 2.5 계수 → 식품군 7~9단계(곡류·채소·과일·달걀·유제품·닭·돼지·소·수산; 육류는 기후솔루션 2026 LCA, 농산물은 농진청, 나머지 국외 DB 명시). 카드는 "오늘 메뉴 vs 주 평균", "저탄소 급식의 날 효과". '추정' 표기 유지, **'실측' 표기 금지**. 잔반 탄소는 잔반 실측 전까지 문헌값(중학생 1인 잔반 79 g 수준, 원문 재확인) + '문헌 추정' 표기.

**P16. 잔반 총량 입력 → 잔반 예보·학급 집단 목표 카드** [창의성·활용성·사회문제] [중(1단계 하)] [1단계 가능] [도메인·UI]
- 1단계: 관리 앱에 일별 잔반 kg 수기 입력(급식실 저울) → 메뉴별 잔반율·탄소 카드 실측화·"내일 잔반 예보"·오늘급식 탄소 절 아래 "이번 주 우리 학교 잔반 목표" 게이지 + 학년/학급 대항 막대(익명), 키오스크에 같은 그래프. 서울시 '잔반제로 대항전' 제출 양식과 맞춤. 2단계(추후): 잔반통 로드셀+ESP32 자동 기록(파일당 writer 규칙 유지). **개인 식판 촬영형 잔반 AI·개인 랭킹은 도입하지 않는다.**

**P17. 익명 메뉴 반응 투표(1일 1회, 3단계)** [창의성·활용성(자율선택급식 데이터)] [하~중] [가능] [도메인]
- 오늘급식에 메뉴별 '좋아요/보통/별로'(기기 로컬 토큰, 집계만 저장) → 인기 보정 입력·자율선택급식(경기 568교) 선호 자료. 공식 만족도 조사(연 1회) 대체가 아님을 명시, 서버에 개인 식별자 저장 금지.

**P18. 이식 패키지 + 법적 근거 문서 세트** [확산↑↑·완성도] [중] [가능] [도메인·ML]
- `site.json`(학교코드·급식실 치수·카메라 모델/화각·급식 창)로 설정 3파일 고정, 보정 **수용 검사**(4점 재투영 오차 임계·λ선 10회 수동 통과 대조·줄 꼬리 화각 포함률), 하드웨어 BOM(20~30만 원/교 추정)·설치 위치 가이드, `insights.db` 스키마 문서 + 일별 CSV 내보내기(선택: OGC SensorThings 매핑).
- **개인정보 서식 세트**: 안내판 문안(목적 "급식 대기 인원 통계 산출 — 영상 미저장", 장소, 촬영 범위·시간=급식 창, 책임자 연락처), 운영·관리 방침 절(실시간 계수 후 즉시 폐기·보관기간 0, 관리자 실사 열람의 범위·10분·감사 기록, 접근권한), 학운위 심의안/설명회·학생 설문 기록 양식, 시행령 §22①1 대응표, 영향평가 체크리스트, 교육청 시범사업 제안서 1장. 매뉴얼 STEP 으로 편입.

**P19. 정확도 외부 검증 + 시차배식 조정 시뮬레이터(간단판)** [완성도·창의성] [중] [부분 가능] [도메인·ML]
- AI Hub '유동 인구 분석 CCTV 영상'(비식별 공개)으로 카운팅 정확도를 산출해 발표 수치로(자체 프레임 저장 없음). 관리자용 "3학년 창을 5분 앞당기면 최대 대기 −N분" 규칙 기반 권고 문장(누적곡선·λ 이용, LLM 문장화) — 2025 수상작의 '예측·행정효율' 경향에 부합.

**P20. 공공데이터 온보딩 자동화·알레르기 아침 알림** [확산·필요성] [중] [설계안/후속] [도메인]
- 학교코드 하나로 NEIS 식단·학교알리미(학생 수·급식 현황)를 받아 `.env`·기준표 자동 생성하는 셋업 화면, 교육청 단위 익명 집계 API 설계안. '내 알레르기 메뉴가 있는 날' 아침 알림(개인 설정은 기기 로컬) — 우선순위 낮음.

---

## 4. 11-11 까지 실행 로드맵(6주 · 추정 공수) 과 결선 서사

| 주차 | 항목 | 산출물 |
|---|---|---|
| 1주(~10/4) | P2 트랙 유예·순유입 λ·진단 지표 → P1 FIFO 추정기(순수 함수+테스트) → 창 밖 시간에 배포 | 체류 실측 매 창 성립, `served_n`·`reappear_n` 열 |
| 2주(~10/11) | P3 실측 프로토콜·`ground_truth`·품질 API, P7·P8(문구·토큰·크기), P13 착석 지표 | 첫 정식 실측 2회, 접근성 검사 기록 |
| 3주(~10/18) | P9 키오스크, P12 투명성 시트·PWA 설치, P14 영양 프리셋, **10-16 수요조사 공문** | 급식실 TV 시범 가동 |
| 4주(~10/25) | P10 주간 리포트 MVP, P15 탄소 계수, P16 잔반 1단계(입력 폼+카드) | 영양교사 인터뷰 1회 반영 |
| 5주(~11/1) | P5 예보 평가·구간·나우캐스트·수축, P11 분산 추천, P17 투표, P4 신뢰도 표시 | 백테스트 표, 신뢰도 3단계 |
| 6주(~11/8) | P18 이식 패키지·법 문서, P19 외부 검증 수치, 구동안내서(mock 경로)·시연영상(실사 없음)·참가신청서, 매뉴얼·layout·WORKLOG 동기화, 공공 GitLab 등록 | **11-11 제출** |
| 병행 | P6 Hailo fps(창 밖 시험) — 결선까지 완료 목표, 미완이면 예비 수치로 발표 | |

**결선(11-26) 발표 서사 제안**: ① 문제 = 식사시간 보장(92% 식당 배식·좌석 회전·착석 20분) → ② 해법 = 카메라가 숫자만 남기는 큐잉 센서(법정 예외 §25①6 설계) → ③ 정확도를 스스로 증명(FIFO 실측·2인 프로토콜·혼동행렬·신뢰도 공개) → ④ 운영 도구(영양교사 리포트·잔반·탄소·분산 추천의 실증) → ⑤ 확산(이식 패키지·서식 세트·교육청 시범사업·초중고 무사례). 예상 질문 대비: "현대그린푸드도 하는데?", "계수 출처는?", "개인정보는?", "정확도는 몇 %?"(→ 방향별·버킷별 범위로 답).

---

## 5. 하지 말 것 (세 관점 합의)

1. 지금 GBM/LSTM 예보 모델을 학습해 넣지 말 것 — 나이브 대비 이득 입증 불가, '딥러닝 예측' 문구는 감점 요인(추정).
2. 외형 임베딩·얼굴 특징을 디스크나 세션을 넘어 저장하지 말 것(시행령 §22①1 요건·§2 원칙). ReID 는 프로세스 메모리 안에서만.
3. 3 fps 그대로 DeepSORT/StrongSORT(CPU ReID)로 갈아타지 말 것 — fps 가 더 떨어져 근본 원인 악화. 순서는 fps↑ → 트래커 실험.
4. 곱셈 보정 K 로 화각 밖 꼬리·발 잘림을 메우지 말 것 — 누락은 배율로 못 살린다(0×K). 커버리지는 Wide·타일 추론·ROI 로, 편향은 FIFO 실측으로 분리.
5. 디즈니식 의도적 과대표시로 분산을 유도하지 말 것 — 학생은 줄에서 직접 검증한다. 분산은 오프셋·범위로.
6. 불확실성 그래프(밀도곡선·오차막대)를 히어로에 넣지 말 것 — 단순 문장·범위·빈도 한 줄.
7. 전교생 동시 푸시("지금 한산!")·개인 잔반 랭킹·개인 식판 촬영형 잔반 AI — 헤딩·낙인·개인정보 원칙 위배.
8. 무지개(jet)·RdYlGn·Spectral 컬러맵, 색만으로 상태 구분, 차트 라이브러리·프레임워크 도입, 스와이프 페이저·히트맵 2열 부활.
9. 급식실 TV 에 실사·마커 영상 송출, 실측을 위한 MJPEG 녹화, 밀집도 타일·positions·L 을 합쳐 개인 궤적을 복원하는 파생 기능.
10. 정확도를 단일 숫자로 발표하지 말 것(MAPE 금지), 그 요일 데이터 3일 미만이면 예보·황금 구간 미게시, 탄소 수치에 '실측' 표기 금지, "미저장이면 개인정보법 대상 아님" 단정 금지(절차는 이행한 위에 미저장을 더했다고 설명).

---

## 6. 재확인 필요 사항 (문서 인용 전)

- 개인정보 보호법 시행령 §22①1 조문 — 국가법령정보센터 원문 대조(이 문서의 요약은 검색 결과 기반).
- 학교 Pi `.env VISION_IMGSZ` 기본 640 여부, Ultralytics HEF 경로에서 `model.track()` 동작 여부(문서 미명시).
- `dwell.forget` 즉시 삭제가 이벤트 0건의 주원인인 비중 — P2 의 `reappear_n` 을 하루 기록해 판명.
- 접근성 대비 수치(2.9:1 등)는 계산값 — 도구(axe/Lighthouse)로 재확인.
- 중학생 1인 잔반 79.2 g, 익산 고등학생 만족도 연구 등 검색 요약 기반 수치는 원문 확인.
- 대회 규정상 학생 팀 저작권·교사 명의 출품 관계, 학교명·학생 정보의 코드/문서 잔존 여부(범정부 공동활용 대비).

---

## 7. 주요 출처

**데이터·ML**: Xovis 공항 큐 https://www.xovis.com/insights/detail/airport-immigration-and-queue-management-use-case · Canon 특허 US10762355B2 https://patents.google.com/patent/US10762355B2/en · US11645895B2 https://patents.google.com/patent/US11645895B2/en · Kim & Whitt TVLL https://www.cambridge.org/core/journals/probability-in-the-engineering-and-informational-sciences/article/abs/estimating-waiting-times-with-the-timevarying-littles-law/18BF94EF65D06A5E52B72D1F81F3BFE0 · Newell 누적곡선 https://eng.libretexts.org/Bookshelves/Civil_Engineering/Fundamentals_of_Transportation/05:_Traffic/5.01:_Queueing · 누적 계수로 대기 분포 복원 https://arxiv.org/abs/2106.00888 · FraMOT https://arxiv.org/abs/2209.11404 · APPTracker https://infzhou.github.io/appTracker/index.html · Roboflow 트래커 벤치 https://trackers.roboflow.com/latest/trackers/comparison/ · Ultralytics bytetrack.yaml https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/cfg/trackers/bytetrack.yaml · botsort.yaml https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/cfg/trackers/botsort.yaml · Hailo‑10H 모델 주 https://github.com/hailo-ai/hailo_model_zoo/blob/master/docs/public_models/HAILO10H/HAILO10H_object_detection.rst · Ultralytics Hailo https://docs.ultralytics.com/integrations/hailo/ · M5 https://www.sciencedirect.com/science/article/pii/S0169207021001874 · Mind the naive forecast https://dl.acm.org/doi/10.1007/s10489-025-06268-w · LH×데이콘 식수 예측 https://dacon.io/competitions/official/235743/overview/description · 대학 식당 식수 예측(KCI 2024) https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003153519 · EnbPI https://arxiv.org/pdf/2010.09107 · 피플카운터 검증 방법론 https://www.ariadne.inc/resources/blogs/people-counter-accuracy-test-methodology/ · 방향별 정확도 https://sensourceinc.com/people-counting/accurate-visitor-counting-system/ · 카메라 이동 감지 https://arxiv.org/html/2310.07886v1 · 개인정보 보호법 §25 https://casenote.kr/%EB%B2%95%EB%A0%B9/%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4_%EB%B3%B4%ED%98%B8%EB%B2%95/%EC%A0%9C25%EC%A1%B0 · 시행령 https://www.law.go.kr/%EB%B2%95%EB%A0%B9/%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4%20%EB%B3%B4%ED%98%B8%EB%B2%95%20%EC%8B%9C%ED%96%89%EB%A0%B9 · 개인정보위 영상기기 안내서(2024.12) https://www.privacy.go.kr/front/bbs/bbsView.do?bbsNo=BBSMSTR_000000000049&bbscttNo=20779 · OpenDataCam https://opendatacam.github.io/opendatacam/ · Telraam https://telraam.net/en/our-traffic-counter · OGC SensorThings https://docs.ogc.org/is/15-078r6/15-078r6.html · 현대그린푸드 https://www.etoday.co.kr/news/view/2443520 · 삼성웰스토리 https://www.upkoreanews.kr/news/articleView.html?idxno=98676

**UI/UX**: Google 인기 시간대 https://blog.google/products-and-platforms/products/maps/maps101-popular-times-and-live-busyness-information/ · 서울 실시간 도시데이터 https://data.seoul.go.kr/dataVisual/seoul/guide.do · 지하철 칸별 혼잡도 https://mediahub.seoul.go.kr/archives/2014362 · 멜버른 응급실 대기표시(RITE) https://www.medrxiv.org/content/10.1101/2022.03.30.22273211v1 · Walker 2021 https://pubmed.ncbi.nlm.nih.gov/32985795/ · 대기 안내 RCT https://pmc.ncbi.nlm.nih.gov/articles/PMC11864359/ · 버스 도착 불확실성(CHI 2016) https://dl.acm.org/doi/10.1145/2858036.2858558 · 홍콩 응급실 시뮬레이션 https://pmc.ncbi.nlm.nih.gov/articles/PMC13197183/ · 오하이오주립대 헤딩 https://arxiv.org/abs/2606.18392 · 바르샤바 RTCI https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8895103/ · Allon 2011 https://pubsonline.informs.org/doi/abs/10.1287/opre.1110.0976 · 디즈니 과대표시 https://mickeyvisit.com/wait-times-at-disney/ · 스웨덴 학급 대항 잔반 https://pmc.ncbi.nlm.nih.gov/articles/PMC10271086/ · FIT Game https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0093872 · 교육부 행복한 교육(잔반 그래프 게시) https://happyedu.moe.go.kr/happy/bbs/selectHappyArticle.do?bbsId=BBSMSTR_000000005043&nttId=7693 · 서울시 잔반제로 대항전 https://go.seoul.co.kr/news/newsView.php?id=20250828500264 · Occuspace 대학 식당 https://www.occuspace.com/case-studies/case-study-university-facility---dining · 사이니지 가독 거리 https://www.signs.com/blog/signage-101-letter-height-visibility/ · Rise Vision 학교 사이니지 https://www.risevision.com/blog/digital-signage-best-practices · WCAG 2.2 신설 https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/ · KWCAG 2.2 https://a11ykr.github.io/kwcag22/ · KRDS 타이포 https://www.krds.go.kr/html/site/style/style_03.html · ColorBrewer https://rdrr.io/cran/RColorBrewer/man/ColorBrewer.html · viridis/cividis https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0199239 · 영국 Analysis Function 대시보드 지침 https://analysisfunction.civilservice.gov.uk/policy-store/data-visualisation-building-and-managing-dashboards/ · 누비랩 리포트 https://www.aitimes.com/news/articleView.html?idxno=166243 · PWA 설치 조건 https://web.dev/articles/install-criteria · 풍부한 설치 UI https://web.dev/articles/web-apps/richer-install-ui · iOS 웹 푸시 제약 https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide · 수업 중 스마트기기 금지법 https://www.korea.kr/news/policyNewsView.do?newsId=148953078

**도메인·정책**: 교실 배식 7.9% https://www.hankookilbo.com/News/Read/A2023101313550004578 · 경기 초등 시차배식 90분 https://www.kgnews.co.kr/news/article.html?no=884833 · 좌석 회전 산식 https://www.lawmeca.com/59445-%ED%95%99%EA%B5%90%EA%B8%89%EC%8B%9D-%EB%95%8C-%ED%95%99%EC%83%9D%EB%93%A4%EC%9D%B4-%EC%8B%9D%EC%82%AC%ED%95%98%EB%8A%94-%EC%8B%9D%EB%8B%B9%EB%A9%B4%EC%A0%81%EC%9D%80-%EC%96%B4%EB%96%BB%EA%B2%8C%EB%90%98%EB%82%98%EC%9A%94/ · JAMA Netw Open 2021 착석 20분 RCT https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2781214 · King County 식사시간·잔반 https://your.kingcounty.gov/dnrp/library/solid-waste/programs/green-schools/food-waste-longer-seated-lunch-periods.pdf · CSPI 2023 https://www.cspi.org/sites/default/files/2023-08/2023%20School%20Food%20Waste%20Fact%20Sheet.pdf · 경기 잔반 6.1만 톤 https://www.kyeongin.com/article/1766793 · 서울 처리비 https://biz.heraldcorp.com/article/3008659 · 중학생 잔반·영양 https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART002811634 · e‑나라지표 급식 인원 https://www.index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd=1543 · 학교급식법 https://law.go.kr/%EB%B2%95%EB%A0%B9/%ED%95%99%EA%B5%90%EA%B8%89%EC%8B%9D%EB%B2%95 · 시행령 https://www.ulex.co.kr/%EB%B2%95%EB%A5%A0/250483-005377-%ED%95%99%EA%B5%90%EA%B8%89%EC%8B%9D%EB%B2%95%EC%8B%9C%ED%96%89%EB%A0%B9 · 2026 학교급식 기본방향(경기) https://www.goe.go.kr/resource/goe/na/bbs_2675/2026/02/29bad70f-478d-472d-aeca-ed9a951a77a4.pdf · 2025 KDRIs 보도 https://www.mohw.go.kr/board.es?mid=a10503010100&bid=0027&act=view&list_no=1488441&tag=&nPage=1 · 영양관리기준 개정 2027 https://www.dhilbo.co.kr/news/articleView.html?idxno=820 · 자율선택급식 https://www.seoul.co.kr/news/politics/local-election2026/2026/05/26/20260526500165 · 저탄소 급식의 날(전남) https://www.fsnews.co.kr/news/articleView.html?idxno=45521 · 영양교사 직무수행도 https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART002069445 · MAR 정의 https://www.anh-academy.org/data4diets/indicator/mean-adequacy-ratio-mar · 국내 탄소계수 현황 https://climateaction.re.kr/news01/1692139 · 기후솔루션 2026 LCA https://forourclimate.org/ko/newsroom/1204 · 누비랩 경기 도입 https://www.fsnews.co.kr/news/articleView.html?idxno=53568 · 대서중 잔반 예보·양심저울 https://www.fsnews.co.kr/news/articleView.html?idxno=55413 · 성지고 예비식 기부 https://www.ohmynews.com/NWS_Web/View/at_pg.aspx?CNTN_CD=A0003234184&PAGE_CD=N0002&BLCK_NO=&CMPT_CD=M0147 · 마산무학여고 학생 개발 https://www.idomin.com/news/articleView.html?idxno=2014124 · 2025 챌린지 결과 https://mois.go.kr/frt/bbs/type013/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000006&nttId=122462 · 학교 CCTV 표준 가이드라인 https://school.jbedu.kr/_cmm/fileDownload/seosu/M010802/079adbdb4be5d661c4c7b086910e7309 · 학교 CCTV 의무화 https://imnews.imbc.com/news/2026/society/article/6800721_36918.html · AI Hub 유동인구 CCTV https://aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&dataSetSn=489 · NEIS 급식 API https://open.neis.go.kr/portal/data/service/selectServicePage.do?page=1&rows=10&sortColumn=&sortDirection=&infId=OPEN17320190722180924242823&infSeq=2 · 학교알리미 API https://www.data.go.kr/data/15098092/openapi.do
