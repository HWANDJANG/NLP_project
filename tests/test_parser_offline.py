"""Offline parser sanity checks using HTML fragments lifted verbatim from
ssodam.com (board 5 list page and a /content/{id} detail page).

Run:
    python -m tests.test_parser_offline
"""
from __future__ import annotations

import sys
from textwrap import dedent

from src.crawler.parser import parse_board_list, parse_post_detail


# -- list-page fragment (익게2, /board/5/1) ----------------------------------
# Three rows: one notice (공지, must skip), one sponsored (제휴, must skip),
# one normal post with [12] comments.
LIST_HTML = dedent(
    """
    <table class='table table-nomargin'>
      <thead><tr><th>제목</th></tr></thead>
      <tbody>
        <tr>
          <td class='title title-align'>
            <span class='label label-info'>공지</span>
            <a href='/content/1987389?prev=1&prev_content=/board/5'>
              <span class=''>AI 규칙</span>
            </a>
          </td>
        </tr>
        <tr>
          <td class='title title-align'>
            <span class='label label-warning'>제휴</span>
            <a href='/content/599248?prev=1&prev_content=/board/5'>
              <span class=''>스폰서드 제목</span>
            </a>
          </td>
        </tr>
        <tr>
          <td class='title title-align'>
            <a href='/content/2023442?prev=1&prev_content=/board/5'>
              <span class='content-title'> 고구려 발해 김치 한복 백두산 vs 독도 </span>
            </a>
            <span class='comment-num'>[12]</span>
          </td>
        </tr>
        <tr>
          <td class='title title-align'>
            <a href='/content/2023440?prev=1&prev_content=/board/5'>
              <span class='content-title'> 하루에 코 50번은 파는데</span>
            </a>
            <span class='comment-num'>[1]</span>
          </td>
        </tr>
      </tbody>
    </table>
    """
)

# -- detail-page fragment (/content/2023442) --------------------------------
# Mirrors the structure observed: title, body, two date elements,
# author self-replies tagged with comment-user-writer, two depth=0
# comments and one depth=1 reply.
DETAIL_HTML = dedent(
    """
    <div class='board-header'>
      <div class='board-title'>고구려 발해 김치 한복 백두산 vs 독도 </div>
      <div class='board-user'>by 익명</div>
      <div class='board-hits'><div class='bar'>|</div>조회&nbsp;174</div>
      <div class='board-date row mobile-hide'>2026/05/17 16:05</div>
      <div class='board-date row col-lg-3 col-xs-12 desktop-hide'>2026/05/17 16:05</div>
    </div>
    <div class='board-content word-break'>
      둘 중 하나 포기해야 한다면 뭐가 좋음?&nbsp;
    </div>
    <div class='board-remove'>
      <div id='watermark'>3359433594</div>
    </div>

    <div id='comments_area_html'>
      <div class="comment" id="comments_13054797">
        <input type="hidden" name="comments_depth" value="0">
        <div class="comment-header">
          <div class="comment-user">익명1</div>
          <div class="comment-date">2026/05/17 16:06</div>
          <div class="comment-date">답글</div>
        </div>
        <div class="word-break comment-content">
          일본 고르게하고싶은 마음은 이해하는데 둘 다 포기할 이유가 전혀없다고 봄
        </div>
      </div>

      <div class="comment" id="comments_13054854">
        <input type="hidden" name="comments_depth" value="1">
        <div class="comment-header">
          <div class="comment-user">글쓴이</div>
          <div class="comment-date">2026/05/17 16:56</div>
          <div class="comment-date">답글</div>
        </div>
        <div class="word-break comment-content comment-user-writer">
          무출산론자는 100년 후 먼 미래까지도 바라봄
        </div>
      </div>

      <div class="comment" id="comments_13054799">
        <input type="hidden" name="comments_depth" value="0">
        <div class="comment-header">
          <div class="comment-user">익명2</div>
          <div class="comment-date">2026/05/17 16:07</div>
          <div class="comment-date">답글</div>
        </div>
        <div class="word-break comment-content">
          ㄹㅇ 다 지켜야지
        </div>
      </div>
    </div>
    """
)


def test_list() -> None:
    stubs = parse_board_list(LIST_HTML)
    ids = [s.post_id for s in stubs]
    assert ids == ["2023442", "2023440"], f"notices not skipped: {ids}"
    s = stubs[0]
    assert s.title == "고구려 발해 김치 한복 백두산 vs 독도", repr(s.title)
    assert s.comment_count_hint == 12, s.comment_count_hint
    assert s.url == "https://www.ssodam.com/content/2023442", s.url
    assert stubs[1].comment_count_hint == 1
    print(f"[list] OK — {len(stubs)} stubs, notices/ads filtered")


def test_detail() -> None:
    d = parse_post_detail(DETAIL_HTML, "2023442",
                          "https://www.ssodam.com/content/2023442")
    assert d is not None, "parser returned None"
    assert d.title.startswith("고구려 발해"), d.title
    assert "포기해야 한다면" in d.body, d.body
    assert d.created_at == "2026/05/17 16:05", d.created_at
    assert d.views == 174, d.views

    assert len(d.comments) == 3
    c1, c2, c3 = d.comments
    assert c1.author == "익명1" and c1.depth == 0 and c1.is_author is False
    assert c2.author == "글쓴이" and c2.depth == 1 and c2.is_author is True
    assert c3.author == "익명2" and c3.depth == 0
    assert "전혀없다고 봄" in c1.text
    assert c1.created_at == "2026/05/17 16:06"
    print(f"[detail] OK — title/body/date/views parsed, {len(d.comments)} comments")


def main() -> int:
    try:
        test_list()
        test_detail()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("\nall offline parser checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
