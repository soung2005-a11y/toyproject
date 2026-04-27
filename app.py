# app.py 코드

import re
from urllib.parse import urlparse, parse_qs

import pandas as pd
import streamlit as st
from zoneinfo import ZoneInfo


st.set_page_config(page_title="유튜브 댓글 가져오기", layout="wide")

st.title("유튜브 댓글 가져오기")
st.caption("주소를 입력하고 버튼을 누르면 인기순 댓글을 가져옵니다.")


def get_youtube_api_key():
    try:
        return st.secrets["youtube_api_key"]
    except Exception:
        return None


@st.cache_resource
def get_youtube_service(api_key):
    from googleapiclient.discovery import build

    return build("youtube", "v3", developerKey=api_key)


def extract_video_id(url):
    if not url:
        return None

    url = url.strip()

    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url):
        return url

    parsed = urlparse(url)

    if not parsed.netloc:
        return None

    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.strip("/")

    if host in ["youtube.com", "m.youtube.com"]:
        query = parse_qs(parsed.query)

        if "v" in query and query["v"]:
            video_id = query["v"][0]
            if re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
                return video_id

        patterns = [
            r"^shorts/([a-zA-Z0-9_-]{11})",
            r"^embed/([a-zA-Z0-9_-]{11})",
            r"^live/([a-zA-Z0-9_-]{11})",
        ]

        for pattern in patterns:
            match = re.search(pattern, path)
            if match:
                return match.group(1)

    if host == "youtu.be":
        video_id = path.split("/")[0]
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
            return video_id

    return None


def convert_to_korea_time(utc_text):
    utc_time = pd.to_datetime(utc_text, utc=True)
    korea_time = utc_time.tz_convert(ZoneInfo("Asia/Seoul"))
    return korea_time.strftime("%Y-%m-%d %H:%M:%S")


def make_csv_for_excel(dataframe):
    return dataframe.to_csv(index=False).encode("utf-8-sig")


def get_popular_comments(youtube, video_id, max_comments=100):
    from googleapiclient.errors import HttpError

    comments = []
    next_page_token = None

    while len(comments) < max_comments:
        try:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                order="relevance",
                textFormat="plainText",
                maxResults=min(100, max_comments - len(comments)),
                pageToken=next_page_token,
            )

            response = request.execute()

        except HttpError as error:
            raise error

        for item in response.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]

            comments.append(
                {
                    "댓글 내용": snippet.get("textDisplay", ""),
                    "작성 시각(한국 시간)": convert_to_korea_time(snippet.get("publishedAt")),
                    "좋아요 수": snippet.get("likeCount", 0),
                }
            )

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    return comments


api_key = get_youtube_api_key()

if not api_key:
    st.error("API키가 없어요. .streamlit/secrets.toml에 넣어 주세요.")

sample_url = "https://www.youtube.com/watch?v=WXuK6gekU1Y"

video_url = st.text_input(
    "유튜브 주소",
    value=sample_url,
    placeholder="유튜브 영상 주소를 입력해 주세요.",
)

run_button = st.button("댓글 가져오기", disabled=api_key is None)

if run_button:
    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("주소가 올바르지 않아요.")
        st.stop()

    try:
        with st.spinner("댓글을 가져오는 중입니다..."):
            youtube = get_youtube_service(api_key)
            comments = get_popular_comments(youtube, video_id)

        if not comments:
            st.warning("가져올 댓글이 없어요.")
            st.stop()

        df = pd.DataFrame(comments)

        st.success(f"댓글 {len(df):,}개를 가져왔어요.")
        st.dataframe(df, use_container_width=True)

        csv_data = make_csv_for_excel(df)

        st.download_button(
            label="CSV 내려받기",
            data=csv_data,
            file_name="youtube_comments.csv",
            mime="text/csv",
        )

    except Exception as error:
        error_text = str(error)

        if "commentsDisabled" in error_text or "disabled comments" in error_text:
            st.error("이 영상은 댓글을 볼 수 없어요.")
        elif "quotaExceeded" in error_text or "dailyLimitExceeded" in error_text:
            st.error("오늘 사용할 수 있는 조회량이 다 됐어요.")
        else:
            st.error("댓글을 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")
