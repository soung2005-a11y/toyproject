# app.py 코드

import re
from urllib.parse import urlparse, parse_qs

import altair as alt
import pandas as pd
import requests
import streamlit as st


st.set_page_config(page_title="유튜브 댓글 시간 분석", layout="wide")

st.title("유튜브 댓글 시간 분석")

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


def get_comment_limit(select_value: str, slider_value: int):
    if select_value == "모두":
        return None

    return max(int(select_value), slider_value)


def utc_to_kst_text(utc_time: str):
    return (
        pd.to_datetime(utc_time, utc=True)
        .tz_convert("Asia/Seoul")
        .strftime("%Y-%m-%d %H:%M:%S")
    )


def utc_to_kst_datetime(utc_time: str):
    return pd.to_datetime(utc_time, utc=True).tz_convert("Asia/Seoul")


def check_youtube_error(response, data):
    if response.status_code == 200:
        return

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


def get_video_upload_time(video_id: str, api_key: str):
    session = get_youtube_session()

    api_url = "https://www.googleapis.com/youtube/v3/videos"

    params = {
        "part": "snippet",
        "id": video_id,
        "key": api_key,
    }

    response = session.get(api_url, params=params, timeout=20)

    try:
        data = response.json()
    except Exception:
        raise ValueError("unknown_error")

    check_youtube_error(response, data)

    items = data.get("items", [])

    if not items:
        raise ValueError("unknown_error")

    upload_time_utc = items[0]["snippet"].get("publishedAt")

    if not upload_time_utc:
        raise ValueError("unknown_error")

    return utc_to_kst_datetime(upload_time_utc)


def get_comments(video_id: str, api_key: str, comment_limit):
    session = get_youtube_session()

    comments = []
    next_page_token = ""

    while True:
        api_url = "https://www.googleapis.com/youtube/v3/commentThreads"

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

        response = session.get(api_url, params=params, timeout=20)

        try:
            data = response.json()
        except Exception:
            raise ValueError("unknown_error")

        check_youtube_error(response, data)

        for item in data.get("items", []):
            top_comment = item["snippet"]["topLevelComment"]["snippet"]

            comment_text = top_comment.get("textDisplay", "")
            published_at = top_comment.get("publishedAt")
            like_count = top_comment.get("likeCount", 0)

            if comment_text and published_at:
                comments.append(
                    {
                        "댓글 내용": comment_text,
                        "작성 시각": utc_to_kst_text(published_at),
                        "작성 시각 원본": utc_to_kst_datetime(published_at),
                        "좋아요 수": like_count,
                    }
                )

            if comment_limit is not None and len(comments) >= comment_limit:
                return comments[:comment_limit]

        next_page_token = data.get("nextPageToken", "")

        if not next_page_token:
            break

    return comments


def make_excel_csv(dataframe: pd.DataFrame):
    csv_df = dataframe[["댓글 내용", "작성 시각", "좋아요 수"]].copy()
    return csv_df.to_csv(index=False).encode("utf-8-sig")


def make_cumulative_data(dataframe: pd.DataFrame):
    time_df = dataframe[["작성 시각 원본"]].copy()
    time_df = time_df.sort_values("작성 시각 원본")
    time_df["누적 댓글 수"] = range(1, len(time_df) + 1)
    time_df["작성 시각"] = time_df["작성 시각 원본"].dt.tz_localize(None)
    return time_df


def find_biggest_increase_time(dataframe: pd.DataFrame, upload_time):
    start_time = upload_time
    end_time = upload_time + pd.Timedelta(days=7)

    seven_days_df = dataframe[
        (dataframe["작성 시각 원본"] >= start_time)
        & (dataframe["작성 시각 원본"] < end_time)
    ].copy()

    if seven_days_df.empty:
        return None

    seven_days_df["시간 단위"] = seven_days_df["작성 시각 원본"].dt.floor("h")
    hourly_df = seven_days_df.groupby("시간 단위").size().reset_index(name="댓글 증가 수")

    if hourly_df.empty:
        return None

    max_row = hourly_df.sort_values("댓글 증가 수", ascending=False).iloc[0]
    return max_row["시간 단위"].tz_localize(None)


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

run_button = st.button("댓글 가져오기 및 분석", disabled=not YOUTUBE_API_KEY)

if run_button:
    video_id = get_video_id(video_url)

    if not video_id:
        st.error("주소가 올바르지 않아요.")
        st.stop()

    comment_limit = get_comment_limit(quick_select, slider_count)

    try:
        with st.spinner("댓글을 가져오고 분석하는 중입니다..."):
            upload_time = get_video_upload_time(video_id, YOUTUBE_API_KEY)
            comments = get_comments(video_id, YOUTUBE_API_KEY, comment_limit)

        if not comments:
            st.info("가져올 댓글이 없어요.")
            st.stop()

        df = pd.DataFrame(comments)
        df = df.sort_values("작성 시각 원본", ascending=True).reset_index(drop=True)

        st.success(f"댓글 {len(df):,}개를 가져왔어요.")

        st.subheader("댓글 표")
        st.dataframe(
            df[["댓글 내용", "작성 시각", "좋아요 수"]],
            use_container_width=True,
        )

        csv_data = make_excel_csv(df)

        st.download_button(
            label="CSV 내려받기",
            data=csv_data,
            file_name="youtube_comments_time_analysis.csv",
            mime="text/csv",
        )

        st.subheader("시간순 누적 댓글 수")
        cumulative_df = make_cumulative_data(df)
        biggest_time = find_biggest_increase_time(df, upload_time)

        line_chart = (
            alt.Chart(cumulative_df)
            .mark_line()
            .encode(
                x=alt.X("작성 시각:T", title="작성 시각"),
                y=alt.Y("누적 댓글 수:Q", title="누적 댓글 수"),
                tooltip=["작성 시각:T", "누적 댓글 수:Q"],
            )
            .properties(height=400)
        )

        if biggest_time is not None:
            rule_df = pd.DataFrame({"증가가 가장 컸던 시점": [biggest_time]})

            rule_chart = (
                alt.Chart(rule_df)
                .mark_rule(color="red", strokeDash=[6, 4], size=2)
                .encode(
                    x=alt.X("증가가 가장 컸던 시점:T"),
                    tooltip=["증가가 가장 컸던 시점:T"],
                )
            )

            st.altair_chart(line_chart + rule_chart, use_container_width=True)
        else:
            st.altair_chart(line_chart, use_container_width=True)

        st.subheader("작성 시각 ↔ 좋아요 수 산점도")
        scatter_df = df.copy()
        scatter_df["작성 시각 차트용"] = scatter_df["작성 시각 원본"].dt.tz_localize(None)

        scatter_chart = (
            alt.Chart(scatter_df)
            .mark_circle(size=70, opacity=0.6)
            .encode(
                x=alt.X("작성 시각 차트용:T", title="작성 시각"),
                y=alt.Y("좋아요 수:Q", title="좋아요 수"),
                tooltip=["댓글 내용", "작성 시각", "좋아요 수"],
            )
            .properties(height=400)
        )

        st.altair_chart(scatter_chart, use_container_width=True)

        st.subheader("시간대(시)별 좋아요 수 합계")
        hour_df = df.copy()
        hour_df["시간대"] = hour_df["작성 시각 원본"].dt.hour
        hour_like_sum = hour_df.groupby("시간대", as_index=False)["좋아요 수"].sum()

        hour_bar_chart = (
            alt.Chart(hour_like_sum)
            .mark_bar()
            .encode(
                x=alt.X("시간대:O", title="시간대(시)"),
                y=alt.Y("좋아요 수:Q", title="좋아요 수 합계"),
                tooltip=["시간대", "좋아요 수"],
            )
            .properties(height=400)
        )

        st.altair_chart(hour_bar_chart, use_container_width=True)

        st.subheader("시간대별 좋아요 분포")
        box_chart = (
            alt.Chart(hour_df)
            .mark_boxplot()
            .encode(
                x=alt.X("시간대:O", title="시간대(시)"),
                y=alt.Y("좋아요 수:Q", title="좋아요 수"),
                tooltip=["시간대", "좋아요 수"],
            )
            .properties(height=400)
        )

        st.altair_chart(box_chart, use_container_width=True)

    except ValueError as error:
        if str(error) == "comments_disabled":
            st.error("이 영상은 댓글을 볼 수 없어요.")
        elif str(error) == "quota_exceeded":
            st.error("오늘 사용할 수 있는 조회량이 다 됐어요.")
        else:
            st.error("댓글을 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")

    except Exception:
        st.error("댓글을 가져오는 중 문제가 생겼어요. 주소와 키를 다시 확인해 주세요.")
