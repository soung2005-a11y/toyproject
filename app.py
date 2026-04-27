# app.py 코드

import re
from urllib.parse import urlparse, parse_qs

import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


st.set_page_config(page_title="유튜브 댓글 가져오기", layout="wide")

st.title("유튜브 댓글 가져오기")

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
        return video_id if video_id else None

    if "youtube.com" in parsed.netloc:
        query = parse_qs(parsed.query)

        if "v" in query:
            return query["v"][0]

        path_parts = [p for p in parsed.path.split("/") if p]

        common_paths = ["shorts", "embed", "live", "v"]
        if len(path_parts) >= 2 and path_parts[0] in common_paths:
            return path_parts[1]

    match = re.search(r"^[a-zA-Z0-9_-]{11}$", url)
    if match:
        return url

    return None


@st.cache_resource
def get_youtube_service(api_key: str):
    return build("youtube", "v3", developerKey=api_key)


def change_to_korea_time(utc_time: str):
    return pd.to_datetime(utc_time, utc=True).tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M:%S")


def get_comments(video_id: str, api_key: str):
    youtube = get_youtube_service(api_key)

    comments = []
    next_page_token = None

    while True:
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            order="relevance",
            textFormat="plainText",
            maxResults=100,
            pageToken=next_page_token,
        )

        response = request.execute()

        for item in response.get("items", []):
            top_comment = item["snippet"]["topLevelComment"]["snippet"]

            comments.append(
                {
                    "댓글 내용": top_comment.get("textDisplay", ""),
                    "작성 시각(한국 시간)": change_to_korea_time(top_comment.get("publishedAt")),
                    "좋아요 수": top_comment.get("likeCount", 0),
                }
            )

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    return comments


def make_csv_for_excel(dataframe: pd.DataFrame):
    return dataframe.to_csv(index=False).encode("utf-8-sig")


sample_url = "https://www.youtube.com/watch?v=WXuK6gekU1Y"

video_url = st.text_input("유튜브 영상 주소", value=sample_url)

button_disabled = not YOUTUBE_API_KEY

run_button = st.button("댓글 가져오기", disabled=button_disabled)

if run_button:
    video_id = get_video_id(video_url)

    if not video_id:
        st.error("주소가 올바르지 않아요.")
        st.stop()

    try:
        with st.spinner("댓글을 가져오는 중입니다..."):
            comment_list = get_comments(video_id, YOUTUBE_API_KEY)

        if not comment_list:
            st.info("가져올 댓글이 없어요.")
            st.stop()

        df = pd.DataFrame(comment_list)

        st.success(f"댓글 {len(df):,}개를 가져왔어요.")

        st.dataframe(df, use_container_width=True)

        csv_data = make_csv_for_excel(df)

        st.download_button(
            label="CSV 내려받기",
            data=csv_data,
            file_name="youtube_comments.csv",
            mime="text/csv",
        )

    except HttpError as error:
        error_text = str(error)

        if "commentsDisabled" in error_text or "forbidden" in error_text:
            st.error("이 영상은 댓글을 볼 수 없어요.")
        elif "quotaExceeded" in error_text:
            st.error("오늘 사용할 수 있는 조회량이 다 됐어요.")
        else:
            st.error("댓글을 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")

    except Exception:
        st.error("댓글을 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")
