import streamlit as st
import pandas as pd
import sqlalchemy
import datetime
import altair as alt
import numpy as np
from streamlit_autorefresh import st_autorefresh
import os

# --- CONFIGURATION ---
DB_URL = "mysql+mysqlconnector://root:Rekie%40123@localhost:3306/email_stats"

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Email Statistics Dashboard",
    page_icon="📧",
    layout="wide"
)

# --- THEME STATE ---
# This function writes the theme to the config.toml file
def set_streamlit_theme(theme):
    """
    Create or update the .streamlit/config.toml file based on
    the selected theme.
    """
    theme_config = {
        "light": {
            "base": "light",
            "primaryColor": "#4CAF50",
            "backgroundColor": "#FFFFFF",
            "secondaryBackgroundColor": "#F0F2F6",
            "textColor": "#000000",
        },
        "dark": {
            "base": "dark",
            "primaryColor": "#4CAF50",
            "backgroundColor": "#000000", # Pure black
            "secondaryBackgroundColor": "#121212",
            "textColor": "#FFFFFF",
        },
    }

    # Ensure .streamlit folder exists
    os.makedirs(".streamlit", exist_ok=True)

    # Write the config file
    config_path = os.path.join(".streamlit", "config.toml")
    with open(config_path, "w") as f:
        f.write("[theme]\n")
        for key, value in theme_config[theme].items():
            f.write(f'{key} = "{value}"\n')

# Session state initialization
if "theme" not in st.session_state:
    st.session_state.theme = "light"  # default mode

# --- TOGGLE FUNCTION ---
def toggle_theme():
    # Flip the theme
    st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"
    # Write the new theme to config.toml
    set_streamlit_theme(st.session_state.theme)
    # Set flag to show refresh message
    st.toast(
        f"Theme set to {st.session_state.theme}. Refresh your browser to apply the full theme.", 
        icon="🎨"
    )

# --- TOGGLE BUTTON ---
st.button("🌙 Toggle Theme", on_click=toggle_theme)
# --- DISPLAY CURRENT THEME ---
st.write(f"🌗 Current Theme: {st.session_state.theme.capitalize()}")
# --- ALTAIR CHART STYLING ---
# This part IS dynamic and will update instantly
def style_chart(chart):
    if st.session_state.theme == "dark":
        alt.themes.enable("dark")
        return chart.configure(
            background="#000000",
            title={"color": "white"},
            axis=alt.Axis(labelColor="white", titleColor="white"),
            legend=alt.Legend(labelColor="white", titleColor="white")
        )
    else:
        alt.themes.enable("default")
        return chart.configure(
            background="#FFFFFF",
            title={"color": "black"},
            axis=alt.Axis(labelColor="black", titleColor="black"),
            legend=alt.Legend(labelColor="black", titleColor="black")
        )

# Auto-refresh the dashboard every 60 minutes
st_autorefresh(interval=60 * 60*1000, key="data_refresher")

# Create the SQLAlchemy engine
@st.cache_resource
def get_engine():
    try:
        return sqlalchemy.create_engine(DB_URL)
    except Exception as e:
        st.error(f"Error connecting to database: {e}")
        st.error("Please ensure your MySQL server is running and the DB_URL is correct.")
        return None
engine = get_engine()

# Function to load data, cached to refresh every 60 seconds
@st.cache_data(ttl=60)
def load_data(start_dt, end_dt):
    if engine is None:
        return pd.DataFrame() 
    query = """
    SELECT * FROM emails 
    WHERE timestamp BETWEEN %(start)s AND %(end)s
    """
    params = {"start": start_dt, "end": end_dt}
    try:
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params=params, parse_dates=['timestamp'])
            df['reply_time_delta'] = pd.to_timedelta(df['reply_time_delta_seconds'], unit='s')
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# --- Dashboard UI ---
st.title("📧 Live Email Statistics Dashboard")
st.header("🗓️ Filter by Time")

today = datetime.date.today()
seven_days_ago = today - datetime.timedelta(days=7)
col1,col2,col3,col4=st.columns(4)
with col1:
    start_date = st.date_input("Start date", seven_days_ago)
with col2:
    end_date = st.date_input("End date", today)

if start_date > end_date:
    st.error("Error: Start date must be before end date.")
    st.stop() 

start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
end_datetime = datetime.datetime.combine(end_date, datetime.time.max)

st.markdown("---")
data = load_data(start_datetime, end_datetime)

if data.empty:
    st.warning("No data found for the selected time range. Please ensure the backend script has been run.")
    st.stop()

# Filter dataframes for convenience
sent_df = data[data['direction'] == 'sent']
received_df = data[data['direction'] == 'received']
reply_df = received_df[received_df['is_reply'] == True]
positive_reply_df = reply_df[reply_df['reply_sentiment'] == 'positive']

## 📊 Top-Level Metrics & Leads
col1, col2, col3, col4 = st.columns(4)
total_sent = sent_df.shape[0]
total_replies = reply_df.shape[0]
total_positive_leads = positive_reply_df.shape[0]
lead_rate = (total_positive_leads / total_sent) * 100 if total_sent > 0 else 0

if reply_df['reply_time_delta'].notna().sum() > 0:
    avg_reply_time_delta = reply_df['reply_time_delta'].mean()
    days = avg_reply_time_delta.days
    hours = avg_reply_time_delta.seconds // 3600
    minutes = (avg_reply_time_delta.seconds % 3600) // 60
    avg_reply_time_str = f"{days}d {hours}h {minutes}m"
else:
    avg_reply_time_str = "N/A"

col1.metric(label="Total Emails Sent", value=f"{total_sent:,}")
col2.metric(label="Total Replies Received", value=f"{total_replies:,}")
col3.metric(label="Total Leads (Positive Replies)", value=f"{total_positive_leads:,}")
col4.metric(label="Lead Rate", value=f"{lead_rate:.2f}%")
st.metric(label="Average Reply Time", value=avg_reply_time_str)
st.markdown("---") 

# --- Time Series Chart ---
st.header("Emails Over Time")
data_grouped = (
    data.set_index('timestamp')
    .groupby([pd.Grouper(freq='D'), 'direction'])
    .size()
    .unstack(fill_value=0)
    .reindex(columns=['sent', 'received'], fill_value=0)
)
chart_df = data_grouped.reset_index().melt(
    id_vars='timestamp',
    var_name='direction',
    value_name='count'
)
chart = (
    alt.Chart(chart_df)
    .mark_line(point=True)
    .encode(
        x=alt.X('timestamp:T', title='Date'),
        y=alt.Y('count:Q', title='Number of Emails'),
        color=alt.Color(
            'direction:N',
            title='Direction',
            scale=alt.Scale(
                domain=['sent', 'received'],
                range=['#1f77b4', '#ff7f0e'] if st.session_state.theme == "light" else ['#4FC3F7', '#FFD54F']
            )
        ),
        tooltip=['timestamp:T', 'direction:N', 'count:Q']
    )
    .properties(
        title='Emails Over Time',
        height=400
    )
)
st.altair_chart(style_chart(chart), use_container_width=True)

## 📈 Lead Insights: Sentiment & Contact
col_chart_1, col_chart_2 = st.columns(2)
with col_chart_1:
    st.subheader("Sentiment Analysis on Received Replies")
    sentiment_data = reply_df.groupby('reply_sentiment').size().reset_index(name='Count')
    if not sentiment_data.empty:
        base = alt.Chart(sentiment_data).encode(theta=alt.Theta("Count", stack=True))
        pie = base.mark_arc(outerRadius=120).encode(
            color=alt.Color("reply_sentiment", 
                            scale=alt.Scale(domain=['positive', 'neutral', 'negative', 'N/A'],
                                            range=['#4CAF50', '#FFC107', '#F44336', '#9E9E9E']), 
                            title="Sentiment"),
            order=alt.Order("Count", sort="descending"),
            tooltip=["reply_sentiment", "Count"]
        )
        text = base.mark_text(radius=140).encode(
            text=alt.Text("Count"),
            order=alt.Order("Count", sort="descending"),
            color=alt.value("white" if st.session_state.theme == "dark" else "black")
        )
        st.altair_chart(style_chart(pie+text), use_container_width=True)
    else:
        st.info("No replies received in this period to analyze sentiment.")

with col_chart_2:
    st.subheader("Lead Rate by Contact Title")
    sent_by_title = sent_df.groupby('contact_title').size().reset_index(name='Total Sent')
    leads_by_title = positive_reply_df.groupby('contact_title').size().reset_index(name='Total Leads')
    lead_rate_df = pd.merge(sent_by_title, leads_by_title, on='contact_title', how='left').fillna(0)
    lead_rate_df['Lead Rate (%)'] = (lead_rate_df['Total Leads'] / lead_rate_df['Total Sent']) * 100
    target_titles = ["Founder","HR Manager", "CTO", "CEO"] 
    chart_data = lead_rate_df[lead_rate_df['contact_title'].isin(target_titles)]
    if not chart_data.empty:
        chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('contact_title', title='Contact Title', sort='-y'),
            y=alt.Y('Lead Rate (%)', title='Lead Rate (%)'),
            color=alt.Color('contact_title', title='Title'),
            tooltip=['contact_title', 'Total Sent', 'Total Leads', alt.Tooltip('Lead Rate (%)', format='.2f')]
        ).properties(
            title='Lead Rate by Key Contact Title'
        )
        st.altair_chart(style_chart(chart), use_container_width=True)
    else:
        st.info(f"No sent data for target titles: {', '.join(target_titles)}")
st.markdown("---")

## 🤖 Reply Funnel: Agent & Time
col_chart_3, col_chart_4 = st.columns(2)
with col_chart_3:
    st.subheader("Lead Rate by AI Agent")
    sent_by_agent = sent_df.groupby('ai_agent').size().reset_index(name='Total Sent')
    leads_by_agent = positive_reply_df.groupby('ai_agent').size().reset_index(name='Total Leads')
    agent_lead_rate_df = pd.merge(sent_by_agent,leads_by_agent,on='ai_agent',how='left').fillna(0)
    agent_lead_rate_df['Lead Rate (%)'] = (agent_lead_rate_df['Total Leads'] / agent_lead_rate_df['Total Sent']) * 100
    agent_lead_rate_df['Lead Rate (%)'].fillna(0, inplace=True)
    agent_lead_rate_df = agent_lead_rate_df.sort_values('Lead Rate (%)', ascending=False)
    chart_data = agent_lead_rate_df[agent_lead_rate_df['Total Sent'] > 0]
    if not chart_data.empty:
        chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('ai_agent', title='AI Agent', 
                    sort=alt.EncodingSortField(field='Lead Rate (%)', op="average", order='descending')), 
            y=alt.Y('Lead Rate (%)', title='Lead Rate (%)'),
            color=alt.Color('ai_agent', title='Agent'),
            tooltip=['ai_agent', 'Total Sent', 'Total Leads', alt.Tooltip('Lead Rate (%)', format='.2f')]
        ).properties(
            title='Lead Rate by AI Agent'
        )
        st.altair_chart(style_chart(chart), use_container_width=True)
    else:
        st.info("No sent email data with a recorded AI agent to calculate lead rate for the selected period.")

with col_chart_4:
    st.subheader("Total Replies by Day of Week")
    reply_df['Day of Week'] = reply_df['timestamp'].dt.day_name()
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    replies_by_day = reply_df.groupby('Day of Week').size().reindex(day_order).fillna(0).reset_index(name='Replies')
    if not replies_by_day.empty:
        chart = alt.Chart(replies_by_day).mark_bar().encode(
            x=alt.X('Day of Week', sort=day_order),
            y=alt.Y('Replies', title='Total Replies Received'),
            tooltip=['Day of Week', 'Replies'],
            color=alt.Color('Day of Week', scale=alt.Scale(domain=day_order), legend=None)
        ).properties(
            title='Replies by Day of Week'
        )
        st.altair_chart(style_chart(chart), use_container_width=True)
    else:
        st.info("No replies received in this period.")
st.markdown("---")

## 🕒 Timing & Distribution Analysis
col_chart_5, col_chart_6 = st.columns(2)
with col_chart_5:
    st.subheader("Replies by Time of Day (Hourly)")
    reply_df['Hour'] = reply_df['timestamp'].dt.hour
    hourly_replies = reply_df.groupby('Hour').size().reset_index(name='Replies')
    if not hourly_replies.empty:
        chart = alt.Chart(hourly_replies).mark_bar().encode(
            x=alt.X('Hour', title='Hour of Day (24hr)'),
            y=alt.Y('Replies', title='Total Replies Received'),
            tooltip=['Hour', 'Replies']
        ).properties(
            title='Replies by Time of Day'
        )
        st.altair_chart(style_chart(chart), use_container_width=True)
    else:
        st.info("No replies received in this period.")

with col_chart_6:
    st.subheader("Positive Reply Time Distribution (Days)")
    valid_reply_times = positive_reply_df['reply_time_delta'].dropna()
    if not valid_reply_times.empty:
        reply_days = np.ceil(valid_reply_times.dt.total_seconds() / (24 * 3600))
        max_days = int(reply_days.max())
        bins = np.arange(1, max_days + 2) 
        hist, edges = np.histogram(reply_days, bins=bins)
        reply_time_dist = pd.DataFrame({
            'Reply Day': [f'Day {int(e)}' for e in edges[:-1]],
            'Reply_Day_Num': [int(e) for e in edges[:-1]],
            'Count': hist
        })
        
        reply_time_dist['Cumulative Count'] = reply_time_dist['Count'].cumsum()
        total_count = reply_time_dist['Count'].sum()
        reply_time_dist['Cumulative Percentage (%)'] = (reply_time_dist['Cumulative Count'] / total_count) * 100
        
        bar_chart = alt.Chart(reply_time_dist).mark_bar().encode(
            x=alt.X('Reply Day', sort=alt.SortField(field='Reply_Day_Num', order='ascending')),
            y=alt.Y('Count', title='No. of Positive Replies'),
            tooltip=['Reply Day', 'Count', alt.Tooltip('Cumulative Percentage (%)', format='.2f')]
        ).properties(
            title='Positive Replies Received By Day After Sent'
        )
        st.altair_chart(style_chart(bar_chart), use_container_width=True)
st.markdown("---")

## 🌍 Geographic & Company Performance
col1,col2=st.columns(2)
with col1:
    st.subheader("Top 10 Responding Companies")
    top_companies = positive_reply_df.groupby('company_name').size().reset_index(name='Positive Replies')
    top_companies = top_companies.sort_values('Positive Replies', ascending=False).head(10)
    if not top_companies.empty:
        # This dataframe will now be themed correctly AFTER a refresh
        st.dataframe(top_companies, use_container_width=True, hide_index=True)
    else:
        st.info("No positive replies to rank companies.")

st.subheader("Reply Rate by Region/City")
sent_by_city = sent_df.groupby('city').size().reset_index(name='Total Sent')
replies_by_city = reply_df.groupby('city').size().reset_index(name='Total Replies')
city_reply_rate_df = pd.merge(sent_by_city, replies_by_city, on='city', how='left').fillna(0)
leads_by_city = positive_reply_df.groupby('city').size().reset_index(name='Total Positive Leads')
city_reply_rate_df = pd.merge(city_reply_rate_df, leads_by_city, on='city', how='left').fillna(0)
city_reply_rate_df['Reply Rate (%)'] = (city_reply_rate_df['Total Replies'] / city_reply_rate_df['Total Sent']) * 100
city_reply_rate_df['Lead Rate (%)'] = (city_reply_rate_df['Total Positive Leads'] / city_reply_rate_df['Total Sent']) * 100
city_reply_rate_df = city_reply_rate_df.sort_values('Lead Rate (%)', ascending=False)
if not city_reply_rate_df.empty:
    st.dataframe(city_reply_rate_df, use_container_width=True, hide_index=True, column_config={
        "Total Sent": "Total Sent",
        "Total Replies": "Total Replies",
        "Total Positive Leads": "Total Leads",
        "Reply Rate (%)": st.column_config.NumberColumn(format="%.2f"),
        "Lead Rate (%)": st.column_config.NumberColumn(format="%.2f"),
    })
else:
    st.info("No sent data to calculate city reply rate.")

st.subheader("Lead Rate by Industry")
funnel_df = sent_df.groupby('company_industry').size().reset_index(name='Total Sent')
replies_by_industry = reply_df.groupby('company_industry').size().reset_index(name='Total Replies')
funnel_df = pd.merge(funnel_df, replies_by_industry, on='company_industry', how='left').fillna(0)
leads_by_industry = positive_reply_df.groupby('company_industry').size().reset_index(name='Total Positive Leads')
funnel_df = pd.merge(funnel_df, leads_by_industry, on='company_industry', how='left').fillna(0)
funnel_df['Reply Rate (%)'] = (funnel_df['Total Replies'] / funnel_df['Total Sent']) * 100
funnel_df['Lead Rate (%)'] = (funnel_df['Total Positive Leads'] / funnel_df['Total Sent']) * 100
funnel_df = funnel_df.sort_values('Lead Rate (%)', ascending=False)
if not funnel_df.empty:
    st.dataframe(funnel_df, use_container_width=True, hide_index=True, 
                    column_config={
                        "Total Sent": "Total Sent",
                        "Total Replies": "Total Replies",
                        "Total Positive Leads": "Total Leads",
                        "Reply Rate (%)": st.column_config.NumberColumn(format="%.2f"),
                        "Lead Rate (%)": st.column_config.NumberColumn(format="%.2f"),
                    })
else:
    st.info("No data to construct the industry conversion funnel.")
st.markdown("---")

*/
</style>

""", unsafe_allow_html=True)
