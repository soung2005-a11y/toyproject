# app.py 코드

import io
import os
import re
import tempfile
from collections import Counter
from urllib.parse import parse_qs, urlparse

import matplotlib.pyplot as plt
import requests
import streamlit as st
from wordcloud import STOPWORDS, WordCloud


st.set_page_config(
    page_title="🎬 유튜브 댓글 워드클라우드",
    page_icon="☁️",
    layout="wide",
)

st.title("🎬 유튜브 댓글 워드클라우드 만들기")
st.info("💡 유튜브 주소와 댓글 수를 입력한 뒤 버튼을 눌러 주세요.")

try:
    YOUTUBE_API_KEY = st.secrets["youtube_api_key"]
except Exception:
    YOUTUBE_API_KEY = None

if not YOUTUBE_API_KEY:
    st.error("🚨 API키가 없어요. .streamlit/secrets.toml에 넣어주세요.")


KOREAN_STOPWORDS = {
    "그리고", "그러나", "하지만", "그래서", "또는", "혹은", "또한", "만약", "비록", "다만",
    "그런데", "근데", "그러면", "그러니", "때문에", "때문", "위해서", "통해서", "대해서",
    "관해서", "관련", "관련된", "경우", "정도", "부분", "내용", "사실", "진짜", "정말",
    "너무", "매우", "아주", "되게", "엄청", "완전", "제일", "가장", "조금", "약간",
    "많이", "계속", "다시", "바로", "이미", "아직", "먼저", "나중", "이제", "요즘",
    "오늘", "어제", "내일", "이번", "저번", "다음", "방금", "항상", "자주", "가끔",
    "언제", "어디", "누가", "누구", "무엇", "뭐가", "뭔가", "어떤", "어떻게", "왜요",
    "이거", "저거", "그거", "이것", "저것", "그것", "여기", "저기", "거기", "이쪽",
    "저쪽", "그쪽", "이런", "저런", "그런", "이렇게", "저렇게", "그렇게", "이게",
    "저게", "그게", "제가", "저는", "나는", "나도", "내가", "너는", "너도", "니가",
    "그는", "그녀", "우리", "저희", "여러분", "사람", "사람들", "누군가", "모두",
    "까지", "부터", "에게", "한테", "께서", "으로", "에서", "보다", "처럼", "만큼",
    "마다", "조차", "마저", "이나", "거나", "하고", "하며", "해서", "하면", "하는",
    "되어", "되는", "됐다", "했고", "했다", "한다", "합니다", "했어요", "있다", "있고",
    "있는", "있음", "없다", "없고", "없는", "없음", "입니다", "이에요", "예요", "같다",
    "같고", "같은", "같아요", "좋다", "좋고", "좋은", "좋아요", "싫다", "싫어", "아님",
    "아니", "아닌", "아니고", "맞다", "맞고", "맞는", "맞아요", "댓글", "영상",
    "유튜브", "구독", "좋아요", "공유", "알림", "채널", "시청", "보고", "보면",
    "보니", "봤다", "봐도", "한번", "정도", "느낌", "생각", "말씀", "이야기",
    "ㅋㅋ", "ㅎㅎ", "ㅠㅠ", "ㅜㅜ", "아하", "오오", "와우", "헐", "음", "네",
    "예", "응", "아니요", "감사", "감사합니다", "수고", "최고", "대박", "그냥",
    "좀", "더", "덜", "또", "꼭", "잘", "못", "왜", "뭐", "와", "및", "등",
}


def get_video_id(url: str):
    url = url.strip()

    if not url:
        return None

    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url):
        return url

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

        if len(path_parts) >= 2 and path_parts[0] in ["shorts", "embed", "live"]:
            video_id = path_parts[1]
            return video_id if re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id) else None

    return None


def clean_filename(text: str):
    text = re.sub(r'[\\/:*?"<>|]', "", text)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text[:80] if text else "youtube_wordcloud"


@st.cache_resource
def get_youtube_session():
    return requests.Session()


@st.cache_resource
def get_korean_font_path():
    font_urls = [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf",
        "https://fonts.gstatic.com/s/nanumgothic/v23/PN_3Rfi-oW3hYwmKDpxS7F_z_tLfxno73g.ttf",
    ]

    font_path = os.path.join(tempfile.gettempdir(), "NanumGothic-Regular.ttf")

    if os.path.exists(font_path) and os.path.getsize(font_path) > 0:
        return font_path

    for font_url in font_urls:
        try:
            response = requests.get(font_url, timeout=20)

            if response.status_code == 200 and len(response.content) > 10000:
                with open(font_path, "wb") as font_file:
                    font_file.write(response.content)

                return font_path
        except Exception:
            continue

    return None


def get_video_title(video_id: str, api_key: str):
    session = get_youtube_session()

    api_url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet",
        "id": video_id,
        "key": api_key,
    }

    response = session.get(api_url, params=params, timeout=20)

    if response.status_code != 200:
        raise ValueError("data_error")

    data = response.json()
    items = data.get("items", [])

    if not items:
        raise ValueError("data_error")

    return items[0]["snippet"].get("title", "youtube_wordcloud")


def get_youtube_comments(video_id: str, api_key: str, max_comments: int):
    session = get_youtube_session()

    comments = []
    next_page_token = ""

    while len(comments) < max_comments:
        api_url = "https://www.googleapis.com/youtube/v3/commentThreads"
        params = {
            "part": "snippet",
            "videoId": video_id,
            "order": "relevance",
            "textFormat": "plainText",
            "maxResults": min(100, max_comments - len(comments)),
            "key": api_key,
        }

        if next_page_token:
            params["pageToken"] = next_page_token

        response = session.get(api_url, params=params, timeout=20)

        try:
            data = response.json()
        except Exception:
            raise ValueError("data_error")

        if response.status_code != 200:
            raise ValueError("data_error")

        for item in data.get("items", []):
            comment = item["snippet"]["topLevelComment"]["snippet"].get("textDisplay", "")
            if comment:
                comments.append(comment)

        next_page_token = data.get("nextPageToken", "")

        if not next_page_token:
            break

    return comments


def make_stopwords(user_korean_stopwords: str, user_english_stopwords: str):
    user_korean_set = {
        word.strip().lower()
        for word in user_korean_stopwords.split(",")
        if word.strip()
    }

    user_english_set = {
        word.strip().lower()
        for word in user_english_stopwords.split(",")
        if word.strip()
    }

    english_stopwords = {word.lower() for word in STOPWORDS}
    korean_stopwords = {word.lower() for word in KOREAN_STOPWORDS}

    return english_stopwords | korean_stopwords | user_korean_set | user_english_set


def make_word_count(comments, stopwords):
    full_text = " ".join(comments).lower()
    words = re.findall(r"[a-zA-Z가-힣]{2,}", full_text)
    words = [word for word in words if word not in stopwords]

    return Counter(words)


def make_wordcloud_image(word_counts, font_path, max_words, max_font_size):
    plt.rcParams["font.family"] = "NanumGothic"

    wordcloud = WordCloud(
        font_path=font_path,
        width=1400,
        height=800,
        background_color="white",
        max_words=max_words,
        max_font_size=max_font_size,
        margin=0,
        collocations=False,
    ).generate_from_frequencies(word_counts)

    figure, axis = plt.subplots(figsize=(14, 8))
    axis.imshow(wordcloud, interpolation="bilinear")
    axis.axis("off")
    figure.tight_layout(pad=0)

    image_buffer = io.BytesIO()
    figure.savefig(image_buffer, format="png", bbox_inches="tight", pad_inches=0, dpi=150)
    image_buffer.seek(0)
    plt.close(figure)

    return image_buffer


sample_url = "https://www.youtube.com/watch?v=WXuK6gekU1Y"

st.subheader("🔗 영상 주소 입력")
video_url = st.text_input("유튜브 영상 주소", value=sample_url)

col1, col2, col3 = st.columns(3)

with col1:
    max_comments = st.number_input(
        "💬 최대 댓글 수",
        min_value=10,
        max_value=5000,
        value=500,
        step=100,
    )

with col2:
    max_font_size = st.slider(
        "🔠 최대 글자수",
        min_value=100,
        max_value=2000,
        value=400,
        step=100,
    )

with col3:
    max_words = st.slider(
        "☁️ 워드클라우드 단어 수",
        min_value=20,
        max_value=200,
        value=100,
        step=10,
    )

with st.expander("🧹 불용어 편집"):
    user_korean_stopwords = st.text_area(
        "추가할 한글 불용어",
        placeholder="예: 영상, 댓글, 진짜",
    )

    user_english_stopwords = st.text_area(
        "추가할 영어 불용어",
        placeholder="예: video, comment, youtube",
    )

run_button = st.button("🚀 댓글 모으고 워드클라우드 만들기", disabled=not YOUTUBE_API_KEY)

if run_button:
    video_id = get_video_id(video_url)

    if not video_id:
        st.error("🚨 주소가 올바르지 않아요.")
        st.stop()

    try:
        with st.spinner("🔎 유튜브 데이터를 가져오는 중입니다..."):
            video_title = get_video_title(video_id, YOUTUBE_API_KEY)
            comments = get_youtube_comments(video_id, YOUTUBE_API_KEY, int(max_comments))

        if not comments:
            st.warning("⚠️ 분석을 진행할 단어를 찾지 못했어요.")
            st.stop()

        with st.spinner("🧹 댓글을 정리하고 단어를 세는 중입니다..."):
            stopwords = make_stopwords(user_korean_stopwords, user_english_stopwords)
            word_counts = make_word_count(comments, stopwords)

        if not word_counts:
            st.warning("⚠️ 분석을 진행할 단어를 찾지 못했어요.")
            st.stop()

        font_path = get_korean_font_path()

        if not font_path:
            st.warning("⚠️ 한글 폰트를 준비하지 못했어요. 워드클라우드 생성을 건너뛰었어요.")
            st.stop()

        with st.spinner("☁️ 워드클라우드를 만드는 중입니다..."):
            image_buffer = make_wordcloud_image(
                word_counts=word_counts,
                font_path=font_path,
                max_words=int(max_words),
                max_font_size=int(max_font_size),
            )

        st.success(f"✅ 댓글 {len(comments):,}개로 워드클라우드를 만들었어요.")

        st.subheader("☁️ 워드클라우드")
        st.image(image_buffer, use_container_width=True)

        file_name = clean_filename(video_title) + "_wordcloud.png"

        st.download_button(
            label="📥 PNG 내려받기",
            data=image_buffer,
            file_name=file_name,
            mime="image/png",
        )

    except Exception:
        st.error("🚨 데이터를 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")
