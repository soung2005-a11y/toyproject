# app.py 코드

import re
from collections import Counter
from urllib.parse import urlparse, parse_qs

import altair as alt
import pandas as pd
import requests
import streamlit as st
from soynlp.tokenizer import RegexTokenizer


st.set_page_config(page_title="유튜브 댓글 단어 분석", layout="wide")

st.title("유튜브 댓글 단어 분석")

try:
    YOUTUBE_API_KEY = st.secrets["youtube_api_key"]
except Exception:
    YOUTUBE_API_KEY = None

if not YOUTUBE_API_KEY:
    st.error("API키가 없어요. .streamlit/secrets.toml에 넣어 주세요.")


def get_video_id(url: str):
    url = url.strip()

    if not url:
        return None

    parsed = urlparse(url)

    if parsed.netloc in ["youtu.be", "www.youtu.be"]:
        video_id = parsed.path.strip("/").split("/")[0]
        return video_id if re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id) else None

    if "youtube.com" in parsed.netloc:
        query = parse_qs(parsed.query)

        if "v" in query:
            video_id = query["v"][0]
            return video_id if re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id) else None

        path_parts = [p for p in parsed.path.split("/") if p]

        if len(path_parts) >= 2 and path_parts[0] in ["shorts", "embed", "live", "v"]:
            video_id = path_parts[1]
            return video_id if re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id) else None

    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url):
        return url

    return None


@st.cache_resource
def get_youtube_session():
    session = requests.Session()
    return session


@st.cache_resource
def get_tokenizer():
    return RegexTokenizer()


def get_comment_limit(select_value: str, slider_value: int):
    if select_value == "모두":
        return None

    return max(int(select_value), slider_value)


def get_comments(video_id: str, api_key: str, comment_limit):
    session = get_youtube_session()

    comments = []
    next_page_token = ""

    while True:
        url = "https://www.googleapis.com/youtube/v3/commentThreads"

        params = {
            "part": "snippet",
            "videoId": video_id,
            "order": "relevance",
            "textFormat": "plainText",
            "maxResults": 100,
            "key": api_key,
        }

        if next_page_token:
            params["pageToken"] = next_page_token

        response = session.get(url, params=params, timeout=20)

        try:
            data = response.json()
        except Exception:
            raise ValueError("unknown_error")

        if response.status_code != 200:
            error_reason = ""

            try:
                error_reason = data["error"]["errors"][0]["reason"]
            except Exception:
                error_reason = ""

            if error_reason in ["commentsDisabled", "forbidden", "videoNotFound"]:
                raise ValueError("comments_disabled")

            if error_reason in ["quotaExceeded", "dailyLimitExceeded"]:
                raise ValueError("quota_exceeded")

            raise ValueError("unknown_error")

        for item in data.get("items", []):
            top_comment = item["snippet"]["topLevelComment"]["snippet"]
            comment_text = top_comment.get("textDisplay", "")

            if comment_text:
                comments.append(comment_text)

            if comment_limit is not None and len(comments) >= comment_limit:
                return comments[:comment_limit]

        next_page_token = data.get("nextPageToken", "")

        if not next_page_token:
            break

    return comments


def clean_word(word: str):
    word = re.sub(r"[^가-힣a-zA-Z0-9]", "", word)
    return word.strip()


def make_word_count(comments):
    tokenizer = get_tokenizer()

    all_words = []

    for comment in comments:
        words = tokenizer.tokenize(comment)

        for word in words:
            clean = clean_word(word)

            if len(clean) >= 2:
                all_words.append(clean)

    counter = Counter(all_words)

    result = pd.DataFrame(counter.most_common(20), columns=["단어", "빈도"])
    return result


sample_url = "https://www.youtube.com/watch?v=WXuK6gekU1Y"

video_url = st.text_input("유튜브 영상 주소", value=sample_url)

col1, col2 = st.columns(2)

with col1:
    quick_select = st.radio(
        "빠른 선택",
        options=["100", "500", "1000", "모두"],
        horizontal=True,
    )

with col2:
    slider_count = st.slider(
        "댓글 개수 슬라이더",
        min_value=100,
        max_value=1000,
        value=100,
        step=100,
    )

run_button = st.button("댓글 가져오기 및 단어 분석", disabled=not YOUTUBE_API_KEY)

if run_button:
    video_id = get_video_id(video_url)

    if not video_id:
        st.error("주소가 올바르지 않아요.")
        st.stop()

    comment_limit = get_comment_limit(quick_select, slider_count)

    try:
        with st.spinner("댓글을 가져오고 단어를 분석하는 중입니다..."):
            comments = get_comments(video_id, YOUTUBE_API_KEY, comment_limit)
            word_df = make_word_count(comments)

        if not comments:
            st.info("가져올 댓글이 없어요.")
            st.stop()

        if word_df.empty:
            st.info("분석할 단어가 없어요.")
            st.stop()

        st.success(f"댓글 {len(comments):,}개를 가져와서 분석했어요.")

        st.subheader("상위 20개 단어 표")
        st.dataframe(word_df, use_container_width=True)

        st.subheader("기본 막대그래프")
        st.bar_chart(word_df.set_index("단어"))

        st.subheader("Altair 막대그래프")
        chart = (
            alt.Chart(word_df)
            .mark_bar()
            .encode(
                x=alt.X("빈도:Q", title="빈도"),
                y=alt.Y("단어:N", sort="-x", title="단어"),
                tooltip=["단어", "빈도"],
            )
            .properties(height=500)
        )

        st.altair_chart(chart, use_container_width=True)

    except ValueError as error:
        if str(error) == "comments_disabled":
            st.error("이 영상은 댓글을 볼 수 없어요.")
        elif str(error) == "quota_exceeded":
            st.error("오늘 사용할 수 있는 조회량이 다 됐어요.")
        else:
            st.error("댓글을 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")

    except Exception:
        st.error("댓글을 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")
