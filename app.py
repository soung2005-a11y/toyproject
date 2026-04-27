# app.py 코드

import re
from urllib.parse import urlparse, parse_qs

import pandas as pd
import streamlit as st
import requests


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

        if len(path_parts) >= 2 and path_parts[0] in ["shorts", "embed", "live", "v"]:
            return path_parts[1]

    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url):
        return url

    return None


@st.cache_resource
def get_youtube_session():
    session = requests.Session()
    return session


def change_to_korea_time(utc_time: str):
    return (
        pd.to_datetime(utc_time, utc=True)
        .tz_convert("Asia/Seoul")
        .strftime("%Y-%m-%d %H:%M:%S")
    )


def get_comments(video_id: str, api_key: str):
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
        data = response.json()

        if response.status_code != 200:
            error_reason = ""

            try:
                error_reason = data["error"]["errors"][0]["reason"]
            except Exception:
                error_reason = ""

            if error_reason in ["commentsDisabled", "forbidden"]:
                raise ValueError("comments_disabled")

            if error_reason in ["quotaExceeded", "dailyLimitExceeded"]:
                raise ValueError("quota_exceeded")

            raise ValueError("unknown_error")

        for item in data.get("items", []):
            top_comment = item["snippet"]["topLevelComment"]["snippet"]

            comments.append(
                {
                    "댓글 내용": top_comment.get("textDisplay", ""),
                    "작성 시각(한국 시간)": change_to_korea_time(top_comment.get("publishedAt")),
                    "좋아요 수": top_comment.get("likeCount", 0),
                }
            )

        next_page_token = data.get("nextPageToken", "")

        if not next_page_token:
            break

    return comments


def make_csv_for_excel(dataframe: pd.DataFrame):
    return dataframe.to_csv(index=False).encode("utf-8-sig")


sample_url = "https://www.youtube.com/watch?v=WXuK6gekU1Y"

video_url = st.text_input("유튜브 영상 주소", value=sample_url)

run_button = st.button("댓글 가져오기", disabled=not YOUTUBE_API_KEY)

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

    except ValueError as error:
        if str(error) == "comments_disabled":
            st.error("이 영상은 댓글을 볼 수 없어요.")
        elif str(error) == "quota_exceeded":
            st.error("오늘 사용할 수 있는 조회량이 다 됐어요.")
        else:
            st.error("댓글을 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")

    except Exception:
        st.error("댓글을 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")
