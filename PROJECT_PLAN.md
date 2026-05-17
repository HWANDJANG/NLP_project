# PROJECT_PLAN.md

# Community-aware Style-controlled Comment Generation

## 1. Project Overview

This project aims to build a **community-aware and style-controlled comment generation system** using online community data.

The initial idea was simple community-style text generation, but the project direction has evolved into a more specific task:

> Generating comments that reflect both:
>
> 1. Community culture (board-specific characteristics)
> 2. Reaction style (aggressive / neutral / friendly)

The system should generate different types of comments for the same post depending on the selected board and style condition.

---

# 2. Main Goal

The goal is not simple comment generation.

The project focuses on:

* Community-aware generation
* Style-controlled generation
* Online reaction modeling

The model should learn how different online communities respond differently to the same topic.

---

# 3. Task Definition

## Input

* Board name
* Post title
* Post content
* Desired reaction style

Example:

```text
[BOARD=취업게시판]
[STYLE=FRIENDLY]
[TITLE=면접에서 떨어졌습니다]
[POST=오늘 면접 결과가 나왔는데 또 떨어져서 너무 우울합니다.]
```

## Output

```text
너무 자책하지 마세요. 면접은 운도 많이 작용합니다.
다음 면접에서는 더 좋은 결과가 있을 거예요.
```

---

# 4. Community Source

The project will crawl data from the following Korean online community website:

* https://www.ssodam.com/index

This website contains multiple boards with different community cultures and interaction styles.

The project will use the following boards:

| Board | Expected Characteristics                             |
| ----- | ---------------------------------------------------- |
| 익게2   | General internet tone, memes, casual reactions       |
| 연애상담소 | Empathy, emotional support, comforting reactions     |
| 정치    | Aggressive, argumentative, confrontational reactions |
| 취업게시판 | Informational, advisory, 현실적인 반응                     |

The goal is to model how the same post receives different reactions depending on the community culture.

---

# 5. Dataset Construction

## Expected Dataset Size

### Posts

```text
300 ~ 500 total posts
```

### Comments

```text
1,500 ~ 3,000 total comments
```

---

## Expected Distribution

| Board | Estimated Posts |
| ----- | --------------- |
| 익게2   | 150             |
| 연애상담소 | 100             |
| 정치    | 80              |
| 취업게시판 | 80              |

---

## Comment Collection Rules

* Only posts with at least 3 comments will be collected
* Average 5 comments per post
* Maximum 10 comments per post
* Prevent overrepresentation of viral/hot posts

---

# 6. Data Format

Initial dataset structure:

```json
{
  "board": "...",
  "title": "...",
  "post": "...",
  "comment": "..."
}
```

Optional metadata:

```json
{
  "post_id": "...",
  "comment_id": "...",
  "created_at": "...",
  "url": "...",
  "comment_count": 5
}
```

---

# 7. Crawling Plan

The first development stage is building a crawling pipeline.

The crawler should:

1. Crawl posts from each selected board
2. Extract:

   * board name
   * post title
   * post content
   * comments
3. Store data in structured JSON/CSV format
4. Handle Korean text encoding correctly (UTF-8)
5. Avoid duplicate posts/comments
6. Respect reasonable crawling intervals

---

# 8. Data Cleaning

The following preprocessing steps will be applied:

* Remove deleted comments
* Remove empty comments
* Remove extremely short comments
* Remove spam-like comments
* Remove duplicated comments/posts
* Remove personal information if necessary
* Normalize whitespace and formatting

Examples of comments to remove:

```text
ㅋㅋ
ㄹㅇ
ㅇㅇ
ㅁㅊ
```

Recommended filtering rule:

```python
len(comment) < 5
```

---

# 9. Style Labels

Each comment will be classified into one of three styles:

| Label      | Description         |
| ---------- | ------------------- |
| Aggressive | 공격적, 비난, 조롱, 명령조    |
| Neutral    | 정보 전달 중심, 감정 표현 적음  |
| Friendly   | 공감, 위로, 존중, 부드러운 조언 |

Ambiguous comments will be labeled as Neutral.

---

# 10. Annotation Plan

* Manually annotate approximately 500~800 comments first
* Use model-assisted or rule-based labeling for the remaining data

The project should prioritize realistic implementation rather than full manual annotation.

---

# 11. Style Classification Model

Before generation, a style classifier will be built.

## Input

```text
comment
```

## Output

```text
Aggressive / Neutral / Friendly
```

## Candidate Models

* TF-IDF + Logistic Regression
* KLUE-BERT
* KoBERT

The classifier will later be reused for evaluating generated comments.

---

# 12. Generation Models

## Baseline Model

Input:

```text
[BOARD] + [TITLE] + [POST]
```

Output:

```text
comment
```

---

## Style-controlled Model

Input:

```text
[BOARD=정치]
[STYLE=AGGRESSIVE]
[TITLE=취업이 너무 힘듭니다]
[POST=요즘 계속 면접에서 떨어지고 있습니다]
```

Output:

```text
솔직히 준비가 부족했던 부분은 없는지 먼저 돌아봐야 할 것 같습니다.
```

---

# 13. Candidate Generation Models

Potential models:

* KoGPT2
* KoT5

Current preference:

```text
KoT5
```

because it naturally supports input-to-output conditional generation.

---

# 14. Experiments

## Experiment 1

Compare:

### Model A

```text
BOARD + TITLE + POST → COMMENT
```

### Model B

```text
BOARD + STYLE + TITLE + POST → COMMENT
```

Research Question:

> Does adding style conditions improve controllability of generated reactions?

---

## Experiment 2

Change only board condition while keeping the same post and style.

Goal:

> Verify whether community-specific reaction patterns emerge.

---

# 15. Evaluation

The project will use three main evaluation methods.

## 1. Style Accuracy

Whether generated comments match the target style.

Measured using the style classifier.

---

## 2. Topic Relevance

Whether generated comments are relevant to the original post.

---

## 3. Human Evaluation

Human evaluators judge:

* Naturalness
* Style consistency
* Community consistency

---

# 16. Final Demo

The final system will function as a:

# Community Reaction Simulator

Users can:

1. Select board
2. Enter title
3. Enter post content
4. Select reaction style
5. Generate comment

The demo may also generate multiple styles simultaneously for the same post.

---

# 17. Core Contribution

The project is not merely text generation.

The main contribution is:

* Modeling online community reaction culture
* Controlling reaction style
* Community-aware conditional comment generation

The project combines:

* Text Classification
* Conditional Text Generation
* Community Modeling
* Style Control
