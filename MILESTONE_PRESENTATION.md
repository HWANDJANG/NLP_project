# Community-aware Style-controlled Comment Generation
**Milestone Presentation**

> 같은 게시글에 대해 **게시판 문화**와 **반응 스타일**을 동시에 반영한 댓글을 생성하는 시스템

---

## 1. Motivation

같은 온라인 게시글이라도 게시판마다 댓글 문화가 다르다.
"면접에서 떨어졌다" 라는 글에는,

- **취업 게시판** → 위로와 현실적 조언
- **정치 게시판** → 비꼬는 반응
- **익명 게시판** → 가벼운 잡담·밈

같은 입력에 대해 게시판·스타일에 따라 **다른 반응**을 생성할 수 있어야 한다는 점에서,
단순한 댓글 생성이 아니라 **조건부(Conditional) 댓글 생성**이 본 프로젝트의 핵심이다.

---

## 2. Task Definition

### Input
```
[BOARD = 취업게시판]
[STYLE = FRIENDLY]
[TITLE = 면접에서 떨어졌습니다]
[POST  = 오늘 면접 결과가 나왔는데 또 떨어져서 너무 우울합니다.]
```

### Output
```
너무 자책하지 마세요. 면접은 운도 많이 작용합니다.
다음 면접에서는 더 좋은 결과가 있을 거예요.
```

### 3가지 조건 (Conditioning)
1. **Board** — 게시판 문화 (4개)
2. **Style** — 반응 스타일 (3-class)
3. **Topic** — 글 제목 + 본문

---

## 3. Data Source

서강대학교 커뮤니티 **서담 (ssodam.com)** 의 4개 게시판을 사용.

| 게시판 | 예상되는 댓글 문화 |
|---|---|
| 익게2 | 밈 / 가벼운 잡담 / 조롱 |
| 연애상담소 | 공감 / 위로 / 조언 |
| 정치 | 논쟁 / 공격적 |
| 취업게시판 | 정보 전달 / 현실 조언 |

이 4개 보드는 같은 사이트에서도 댓글 톤이 크게 다를 것이라는 가설을 가지고 선정.

---

## 4. Crawling Pipeline

### URL 구조 분석
- 목록: `/board/{board_id}/{page}` (path-segment 방식)
  - 익게2=5, 연애상담소=6, 정치=86, 취업게시판=11
- 상세: `/content/{post_id}`

### 구현 (`src/crawler/`)
- `requests` + `BeautifulSoup` (정적 HTML)
- 세션 쿠키 인증 (`.env` 의 `SSODAM_COOKIE`)
- **truststore** 로 SSL 인증서 검증 해결 (Windows 시스템 CA 사용)
- 요청 간 1.5초 polite delay
- **사전 필터링**: 목록 페이지에서 댓글 수가 3개 미만인 글은 상세 fetch 생략 → 트래픽 절감
- 작성자 본인 댓글(`글쓴이`)은 자기 글 설명이므로 제외
- 게시판별 JSONL 저장 (`data/raw/{board}.jsonl`), 중단·재개 시 `post_id` 중복 자동 스킵

### 수집 결과 (약 18분 소요)
| 게시판 | 게시글 | 댓글 | 글당 평균 |
|---|---:|---:|---:|
| 익게2 | 150 | 938 | 6.25 |
| 연애상담소 | 100 | 674 | 6.74 |
| 정치 | 80 | 372 | 4.65 |
| 취업게시판 | 80 | 439 | 5.49 |
| **합계** | **410** | **2,423** | **5.91** |

→ PROJECT_PLAN 목표(300~500 글 / 1,500~3,000 댓글) 범위 내에 정확히 안착.

---

## 5. Manual Labeling

### 라벨 스킴
| 라벨 | 의미 | 기준 |
|---|---|---|
| **s** | Supportive | 공감, 위로, 응원, 정서적 지지 |
| **i** | Informative | 정보 전달, 조언, 경험 공유, 일반 의견 (기본값) |
| **c** | Critical | 공격, 조롱, 비난, 냉소, 무시 (강한 공격성에만) |
| **d** | Delete | 삭제된 댓글, 의미 없는 댓글 (제외) |

→ PROJECT_PLAN 의 Aggressive / Neutral / Friendly 와 1:1 매핑.

### 라벨링 정책
- 애매한 경우 모두 `i`
- `c` 는 강한 공격성에만 부여 → 보수적 labeling
- 본인 단독 annotator (single annotator)
- 학습용 최종: **2,393개** (d=30 제외)

### 변환 결과 (`src/preprocessing/load_labels.py`)
`data/labeling/comments_to_label.xlsx` → `data/labeled/comments_labeled.{jsonl,csv}`

| label | count | 비율 |
|---|---:|---:|
| i (Informative) | 2,038 | 85.2% |
| c (Critical) | 273 | 11.4% |
| s (Supportive) | 82 | 3.4% |

> **이미 이 단계에서 클래스 불균형이 매우 큰 것이 보임 (i:s ≈ 25:1)** — 후속 모델링에 중요한 제약.

---

## 6. Exploratory Data Analysis

### 6-1. 게시판 × 라벨 cross-tab (핵심 발견)

| 게시판 | s (지지) | i (정보) | c (비판) | total |
|---|---:|---:|---:|---:|
| 익게2 | 8 (0.9%) | 811 (87.9%) | 104 (11.3%) | 923 |
| 연애상담소 | 36 (5.4%) | 589 (88.3%) | 42 (6.3%) | 667 |
| **정치** | **1 (0.3%)** | 272 (73.1%) | **99 (26.6%)** | 372 |
| 취업게시판 | **37 (8.6%)** | 366 (84.9%) | 28 (6.5%) | 431 |

**가설 검증** — 게시판마다 통계적으로 명확히 다른 댓글 문화:
- **정치**: Supportive 단 1건, Critical 26.6% → 가장 공격적
- **취업게시판**: Supportive 8.6% → 가장 응원 문화 (면접 위로 등)
- **연애상담소**: Supportive 5.4% → 공감 중심
- **익게2**: Critical 11.3% (정치보단 낮지만 가벼운 조롱 문화)

→ "같은 사이트 안에서도 게시판별 반응 문화가 통계적으로 다르다" 는 PROJECT_PLAN의 핵심 가설을 **데이터로 실제 입증**.

### 6-2. 댓글 길이 분포
- 게시판별 중앙값 — 익게2 22자 / 연애상담소 28자 / 정치 24자 / 취업 26자
- **연애상담소가 가장 길고 분포 폭이 넓음** (긴 진심 토로 댓글 다수, max 984자)
- 라벨별 중앙값 — **s: 31.5자 (가장 길다)** / i: 24 / c: 23
- → 위로(s) 는 길게 쓰는 경향, 조롱(c) 은 한 줄로 짧게

### 6-3. 시각 자료 (`reports/eda/`)
1. `01_counts_per_board.png` — 게시판별 게시글/댓글 수
2. `02_label_share_per_board.png` — 게시판별 스타일 비율 (stacked bar)
3. `03_comment_length_per_board.png` — 게시판별 길이 boxplot
4. `04_comments_per_post.png` — 글당 댓글 수 분포
5. `05_length_by_label.png` — 라벨별 길이 boxplot

---

## 7. Style Classifier Experiments

### 7-1. Baseline: TF-IDF + Logistic Regression (3-class)

#### 설정
- 벡터화: `TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4))`
  - 한국어 형태소 분석기 없이 char n-gram 사용 (subword signal)
- 모델: `LogisticRegression(class_weight="balanced", solver="lbfgs")`
- 평가: 5-fold StratifiedKFold + held-out test 20%

#### 결과
| 지표 | 값 |
|---|---|
| 5-fold CV macro-F1 | **0.568 ± 0.055** |
| 5-fold CV weighted-F1 | 0.835 ± 0.019 |
| Test set accuracy | 83.5% |

| label | precision | recall | F1 | n |
|---|---:|---:|---:|---:|
| s | 0.455 | 0.312 | 0.370 | 16 |
| i | 0.882 | 0.936 | **0.908** | 408 |
| c | 0.371 | 0.236 | 0.289 | 55 |

#### 진단 (냉정한 평가)
- **majority baseline (전부 i 예측) 정확도 = 85.2%** > 우리 모델 83.5%
- 즉, 정확도 기준으로는 **dummy보다 못한 모델**
- macro-F1 0.57 vs dummy 0.31 → "i 정확도 양보 + s/c 일부 맞춤" trade-off
- minority recall이 22~31% → 실용 불가
- s↔c 사이 오분류는 거의 없음 → 모델이 "감정 방향"보단 "강도(중립화)" 학습

### 7-2. 진단 후 가설 검증: 2-class 재구성

> "3-class가 너무 미세한 것이 원인일 수 있다 → 단순화하면 회복되는가?"

| Task | CV macro-F1 | positive-F1 | Test acc | majority acc |
|---|---:|---:|---:|---:|
| 3-class (참고) | 0.568 | s=0.37 / c=0.29 | 83.5% | 85.2% |
| **A. Critical vs Non-Critical** | 0.670 | c=0.407 | 87.3% | 88.6% |
| **B. Subjective vs Informative** | 0.667 | (s∪c)=0.424 | 84.6% | 85.2% |

#### 의미
- macro-F1 **0.57 → 0.67 (+10%p)** 개선 — 단순화는 도움
- 그러나 **두 task 모두 여전히 majority baseline 정확도를 못 넘음**
- Critical recall은 22% 그대로
- **결론**: 모델 표현력이 아니라 **minority 클래스의 절대 데이터량(c=273, s=82) 부족이 천장**

### 7-3. KLUE-BERT Fine-tuning

#### 설정
- Backbone: `klue/bert-base` (110M params, 한국어 BPE)
- Class-weighted cross-entropy (s/c 보강)
- 60/20/20 stratified split (train=1,435, val=479, test=479)
- max_len=96, batch=16, lr=2e-5, epoch 4, early stopping
- CPU 학습 (MX250 2GB는 OOM 위험) — 약 55분 소요

#### 결과 (held-out test 20%)
| label | precision | recall | F1 | n |
|---|---:|---:|---:|---:|
| s · Supportive | 0.444 | **0.500** | **0.471** | 16 |
| i · Informative | 0.908 | 0.873 | 0.890 | 408 |
| c · Critical | 0.391 | **0.491** | **0.435** | 55 |
| **macro avg** | 0.581 | **0.621** | **0.599** | 479 |
| accuracy | | | 0.816 | |

Confusion matrix (rows=true, cols=pred — order: s/i/c)
```
[[  8   8   0]      ← s: 절반 맞춤(8/16), c로 흘러간 건 0
 [ 10 356  42]      ← i: 87% recall (baseline 94%에서 양보)
 [  0  28  27]]     ← c: 절반 맞춤(27/55), s로 가는 건 0
```

#### Baseline vs KLUE-BERT 비교

| 지표 | Baseline (TF-IDF+LR) | KLUE-BERT | Δ |
|---|---:|---:|---:|
| accuracy | 0.835 | 0.816 | −1.9%p |
| **macro-F1** | 0.523 | **0.599** | **+7.6%p** |
| s recall | 0.312 | **0.500** | **+18.8%p** |
| s F1 | 0.370 | **0.471** | +10.1%p |
| c recall | 0.236 | **0.491** | **+25.5%p** |
| c F1 | 0.289 | **0.435** | +14.6%p |
| i F1 | 0.908 | 0.890 | −1.8%p |

#### 해석
- **Minority recall이 거의 두 배로 회복** — 사전학습 효과 분명히 존재
- BERT는 "i를 약간 양보하고 s/c를 살리는" 방향으로 학습됨
- **그러나 여전히 majority baseline accuracy(85.2%)를 못 넘음**
- s/c 모두 recall 50% 수준 → 실용 가능 수준(70%+)까지는 데이터 추가가 필요
- **가설 수정**: "데이터 절대량이 유일한 천장" → "데이터 + 모델 표현력 둘 다 영향. BERT가 데이터 부족 일부를 보완하지만 절대값은 여전히 부족"

### 7-4. Data Augmentation Pipeline (Gemini, 진행 중)

> "데이터를 늘리면 minority가 정말 회복되는가?" 를 중간발표까지 빠르게 검증하기 위한 LLM 증강.

#### 파이프라인 (4단계)
```
원본 2,393개
  │
  ├─[1] split 고정 ──→ train 60% / val 20% / test 20%   (split.json 에 comment_id 저장)
  │
  ├─[2] 증강 ────────→ train 의 s/c 만 Gemini paraphrase  (val/test 는 손대지 않음)
  │                     s ×3, c ×2  (s 가 더 부족 → 더 크게)
  │
  ├─[3] 재학습 ──────→ (원본 train + 증강분) 으로 KLUE-BERT
  │
  └─[4] 평가 ────────→ 원본 test 로 측정 → 증강 전/후 비교
```

#### 방법론 원칙 (성능 부풀리기 방지)
1. split 을 먼저 고정하고 `data/labeled/split.json` 으로 저장 → 모든 실험 동일 split, 데이터 누수 0
2. **train 의 s/c 만** 증강, **val/test 는 원본 real 댓글만**
3. paraphrase 는 원본 라벨 상속, 프롬프트로 감정·스타일·강도 보존 지시
4. 발표·평가 시 "augmented train, evaluated on held-out real comments" 명시

#### 안전장치
- Rate limit: 요청 간 sleep + 429 시 exponential backoff
- 중단 재개: 생성분 캐시(jsonl append), 재실행 시 건너뜀
- 품질 필터: 원본과 동일하거나 5자 미만인 결과 폐기

#### 실행
```powershell
python -m src.augmentation.make_split          # 1) split 고정
python -m src.augmentation.augment_gemini      # 2) Gemini 증강
python -m src.classifier.klue_bert --augmented # 3) 재학습 + 4) 원본 test 평가
```

#### 실제 증강 규모
- train s/c 211개 댓글을 paraphrase → **470개 생성** (s +147, c +323)
- train 분포: s 50→**197**, c 163→**486**, i 1,222 (불변) → 불균형 25:3.3:1 → 6:2.5:1

#### 결과 (동일 원본 test 479개, val/test 모두 원본)
| 지표 | 증강 전 (원본만) | 증강 후 (s×3 c×2) | Δ |
|---|---:|---:|---:|
| macro-F1 | **0.599** | 0.554 | **−0.045** |
| accuracy | 0.816 | 0.802 | −0.014 |
| s recall | 0.500 | 0.500 | = |
| s F1 | 0.471 | 0.444 | −0.027 |
| **c recall** | **0.491** | 0.345 | **−0.146** |
| **c F1** | **0.435** | 0.336 | **−0.099** |
| i F1 | 0.890 | 0.883 | −0.007 |

증강 후 confusion (rows=true, order s/i/c): `[[8,8,0],[12,357,39],[0,36,19]]`
→ c 를 27/55 맞추던 것이 19/55 로 떨어지고 그만큼 i 로 오분류됨.

#### 해석 — **증강은 역효과 (negative result)**
- LLM paraphrase 는 **표현(어휘·어미) 다양성**은 더하지만 **의미·맥락 다양성**은 더하지 못함
- train 의 c 가 "원본 163개의 변주 486개"로 부풀려지며 **어휘 패턴이 균질화** → 좁은 분포에 과적합 → test 의 실제 다양한 c 를 놓침
- Gemini 가 공격적 댓글을 전형적 톤으로 수렴시키는 경향 → 실제 커뮤니티 c 의 미묘함과 괴리
- s 는 표현 폭이 원래 좁아 증강해도 새 신호 없음 (recall 0.50 불변)
- ⚠️ 단일 run 기준 — 변동성 일부 있을 수 있으나 c recall 하락폭(−0.146)이 커 증강 부작용으로 판단

> **결론: 합성 증강 < 자연 데이터.** 이 negative result 가 발표 후 "실제 추가 크롤링 + 직접 라벨링" 계획의 필요성을 실증적으로 정당화한다.

---

## 8. Findings & Trial-and-Error Narrative

### Phase 1. 데이터 수집 — 큰 마찰 없이 통과
- SSL 인증서 검증 실패 → `truststore` 한 줄로 해결
- 목록 페이지 사전 필터로 트래픽 절감 (댓글 < 3 글 스킵)
- 18분 만에 410글 / 2,423댓글 수집 완료

### Phase 2. 라벨링 — 보수적 정책의 양날
- "애매하면 i" 정책으로 일관성 확보
- 그러나 결과적으로 s/c 의 데이터 절대량이 매우 적어짐 (s=82, c=273)
- **이것이 이후 모든 모델링의 천장이 됨**

### Phase 3. Baseline 실패 → 진단
- "TF-IDF + LR macro-F1 0.57은 합리적인 baseline" 으로 보였음
- 그러나 dummy 정확도(85.2%) > 모델 정확도(83.5%) 라는 사실 발견
- → "표면적 macro-F1 개선" 과 "실용성" 의 괴리

### Phase 4. 가설 검증: 단순화로 회복?
- 3-class → 2-class 단순화로 macro-F1 0.67 까지 회복
- 그러나 majority 정확도 못 넘음, minority recall 22% 그대로
- → 문제는 모델이 아니라 **데이터 절대량**임이 정량적으로 확인됨

### Phase 5. 사전학습 모델 도입 → 가설 일부 수정
- KLUE-BERT 도입 결과:
  - macro-F1 **0.523 → 0.599 (+7.6%p)**
  - **minority recall 거의 두 배 회복** (s 31→50%, c 24→49%)
  - 다만 absolute recall은 여전히 50% 수준 → 실용 단계 미달
  - majority baseline accuracy(85.2%)는 여전히 못 넘음
- **가설 수정**: "데이터 절대량만이 천장" → "데이터 부족 + 모델 표현력 둘 다 영향"
- **다음 액션 결정 근거**: BERT가 적은 데이터로도 minority를 어느 정도 살리는 걸 보면, 데이터를 추가/증강하면 BERT는 더 끌어올릴 여지가 큼 → 데이터 증강이 다음 우선순위

### Phase 6. 데이터 증강 → negative result → 방향 재확정
- 중간발표까지 시간 제약 → 직접 추가 크롤링·전수 라벨링(수 시간)보다 **LLM 증강을 먼저** 수행하기로 결정
- **Gemini(gemini-2.5-flash)로 train split의 s/c 댓글만 paraphrase** → 470개 생성 (s 50→197, c 163→486)
- **결과: 오히려 하락** — macro-F1 0.599→0.554, **c recall 0.49→0.35**
  - paraphrase 가 표현은 바꾸지만 의미·맥락 다양성을 못 더해 train 분포가 인공적으로 편향됨
  - 합성 증강의 한계를 실증 → **자연 데이터 추가 수집의 필요성을 역설적으로 입증**
- 방법론은 정확히 지킴: split 먼저 고정(`split.json`), train s/c 만 증강, val/test 는 원본 real 댓글만, "augmented train / real test" 명시
- **다음 방향 재확정**: 발표 후 정치(c)·취업·연애(s) 추가 크롤링 + 직접 라벨링으로 자연 분포 확보

<details><summary>증강 방법론 원칙 (성능 부풀리기 방지)</summary>

  1. 원본 2,393개를 먼저 train/val/test로 split
  2. **train 안의 s/c만** 증강
  3. **val/test는 원본 real 댓글만** 유지 (증강 문장 절대 미포함)
  4. 평가·발표 시 "augmented train, evaluated on held-out real comments" 명시

</details>

---

## 9. Next Steps

### 발표 전 — 모두 완료 ✅
1. ✅ **KLUE-BERT 결과 확정** 및 baseline 비교 (macro-F1 0.523→0.599)
2. ✅ **Gemini API 데이터 증강 (train-only)** — 470개 생성, train s 50→197 / c 163→486
3. ✅ **증강 데이터로 재학습 → 원본 test 평가** — 결과: macro-F1 0.599→0.554 (**negative result**)
4. ✅ 증강 전/후 비교표 (§7-4) — 발표에 negative result로 포함

### 발표 후 (자연 데이터 보강) — negative result로 정당화됨
5. **추가 크롤링 + 직접 라벨링** — 정치(c), 취업/연애(s) 집중 수집해 자연 분포 확보
   - 합성 증강이 실패했으므로 **자연 데이터가 유일한 현실적 보강책**
   - 게시판별 균형은 불필요 (분류기는 board를 안 봄), c/s 총량만 목표
   - 목표: c ~500, s ~300 (자연 데이터)
6. **라벨 일관성 sanity check** — s/c 일부 재검토
7. (선택) 증강 재시도 — temperature↑·다양성 프롬프트·배수 조정으로 over-fitting 완화 여부 확인

### 생성 모델 (중기)
7. **KoT5 conditional generator** 학습
   - Input: `[BOARD] [STYLE] [TITLE] [POST]` → Output: comment
   - 비교 실험: 스타일 조건 유무 (Model A vs B)
   - 비교 실험: 게시판 조건 변경 효과
8. **평가**
   - Style accuracy: 위에서 만든 스타일 분류기로 자동 평가
   - Topic relevance: BLEU / BERTScore
   - Human evaluation: 자연스러움, 스타일/커뮤니티 일치도

### 데모 (장기)
9. **Community Reaction Simulator** — 같은 글에 s/i/c 3가지 댓글을 동시에 생성하는 데모 (Streamlit / Gradio)

---

## 10. Project Structure

```
ProjectFile/
├── PROJECT_PLAN.md               # 전체 프로젝트 기획
├── MILESTONE_PRESENTATION.md     # 이 문서
├── requirements.txt
├── .env.example                  # SSODAM_COOKIE, GEMINI_API_KEY 템플릿
│
├── src/
│   ├── crawler/                  # ssodam 크롤링
│   ├── preprocessing/            # JSONL ↔ CSV, 라벨 로딩
│   ├── augmentation/             # (예정) Gemini paraphrase 증강 (train-only)
│   ├── eda/                      # 차트·통계
│   └── classifier/               # baseline, baseline_2class, klue_bert
│
├── data/
│   ├── raw/                      # 4개 게시판 JSONL (게시글 + 댓글)
│   ├── labeling/                 # 라벨링용 CSV/XLSX
│   └── labeled/                  # 학습용 깨끗한 JSONL/CSV
│
├── reports/
│   ├── eda/                      # 차트 PNG 5장
│   └── classifier/               # 모델 metrics, confusion matrix
│
└── tests/                        # 파서 회귀 테스트
```

---

## 11. 핵심 메시지 (발표 한 줄 정리)

> **"같은 사이트 안에서도 게시판마다 댓글 문화가 통계적으로 명확히 다르다는 점을 데이터로 입증했고,
> baseline 실패를 정량적으로 진단(majority < 모델 정확도) → 2-class 재구성으로 문제 절반 해결 →
> KLUE-BERT로 minority recall 두 배 회복 → LLM 증강은 오히려 역효과(negative result)임을 확인하는
> 시행착오를 거쳐, 합성 데이터의 한계를 실증하고 자연 데이터 추가 수집의 필요성을 정당화했다."**

### 발표 슬라이드 흐름 권장 (10~12장)
1. 표지 / 한 줄 motivation
2. Task definition (input/output 예시)
3. 데이터 출처 (ssodam 4보드)
4. 크롤링 파이프라인 한 장 (수집 결과 표)
5. 라벨링 스킴 + 분포
6. EDA — 게시판 × 라벨 cross-tab (가장 강한 슬라이드)
7. EDA — 댓글 길이 분포
8. Baseline 결과 + 진단 ("dummy보다 못한 모델")
9. 2-class 재구성 시도 + 결과
10. KLUE-BERT 도입 + 비교 표
11. 데이터 증강 전략 + 증강 전/후 비교 (Gemini, train-only / 원본 test 평가)
12. 다음 단계 (자연 데이터 보강 → KoT5 generator) + 한 줄 요약
