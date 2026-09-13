import streamlit as st
import pandas as pd
import datetime
import gspread
from google.oauth2.service_account import Credentials
import plotly.graph_objects as go
import plotly.express as px

# =========================================================
# PAGE CONFIGURATION & THEME
# =========================================================
st.set_page_config(
    page_title="سیستم ژورنال معاملاتی هوشمند",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# CUSTOM DARK / MODERN TRADING CSS
# =========================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Vazirmatn:wght@300;400;600;700&display=swap');
    
    * {
        font-family: 'Vazirmatn', sans-serif;
    }
    
    code, .metric-value, span[data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', 'Vazirmatn', monospace !important;
    }

    /* Backgrounds and Cards */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #0e1117;
        border: 1px solid #1f2937 !important;
        border-radius: 12px !important;
        padding: 16px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.25);
        margin-bottom: 1rem;
    }

    /* Metric Cards */
    div[data-testid="metric-container"] {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    
    /* Inputs Styling */
    .stTextInput input, .stNumberInput input, .stSelectbox select, .stTextArea textarea {
        background-color: #161b22 !important;
        color: #f0f6fc !important;
        border: 1px solid #30363d !important;
        border-radius: 8px !important;
    }

    /* Badges */
    .badge-grade {
        display: inline-block;
        padding: 6px 14px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 1rem;
        letter-spacing: 0.5px;
    }
    .badge-aplus {
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid #10b981;
        color: #34d399;
    }
    .badge-b {
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid #3b82f6;
        color: #60a5fa;
    }
    .badge-notrade {
        background: rgba(239, 68, 68, 0.15);
        border: 1px solid #ef4444;
        color: #f87171;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# DATABASE & GOOGLE SHEETS HELPERS (SAFE UPSERT LOGIC)
# =========================================================
def generate_trade_id():
    now = datetime.datetime.now()
    return f"TRD-{now.strftime('%Y%m%d-%H%M%S')}"

@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials_dict = dict(st.secrets["connections"]["gsheets"])
    if "private_key" in credentials_dict:
        credentials_dict["private_key"] = credentials_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(creds)

def get_worksheet():
    gc = get_gspread_client()
    sheet_target = st.secrets["connections"]["gsheets"]["spreadsheet"].strip()
    sh = gc.open_by_url(sheet_target) if sheet_target.startswith("http") else gc.open_by_key(sheet_target)
    try:
        return sh.worksheet("Sheet1")
    except Exception:
        return sh.get_worksheet(0)

@st.cache_data(ttl=30)
def load_data():
    try:
        ws = get_worksheet()
        values = ws.get_all_values()
        if not values or len(values) < 2:
            return pd.DataFrame()
        return pd.DataFrame(values[1:], columns=values[0])
    except Exception:
        return pd.DataFrame()

def upsert_trade(trade_record: dict):
    try:
        ws = get_worksheet()
        values = ws.get_all_values()
        trade_id = str(trade_record.get("Trade ID", "")).strip()
        
        if not values or len(values) == 0:
            headers = list(trade_record.keys())
            ws.append_row(headers)
            ws.append_row([str(trade_record.get(h, "")) for h in headers])
            st.cache_data.clear()
            return True

        headers = values[0]
        updated_headers = list(headers)
        for k in trade_record.keys():
            if k not in updated_headers:
                updated_headers.append(k)

        if updated_headers != headers:
            ws.update(range_name="A1", values=[updated_headers])
            headers = updated_headers

        trade_id_idx = headers.index("Trade ID") if "Trade ID" in headers else 0
        existing_row_index = None

        for idx, row in enumerate(values[1:], start=2):
            if len(row) > trade_id_idx and str(row[trade_id_idx]).strip() == trade_id:
                existing_row_index = idx
                break

        ordered_row = [str(trade_record.get(col, "")) for col in headers]

        if existing_row_index:
            col_letter = gspread.utils.rowcol_to_a1(existing_row_index, len(headers))
            ws.update(range_name=f"A{existing_row_index}:{col_letter}", values=[ordered_row])
        else:
            ws.append_row(ordered_row)

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"خطا در همگام‌سازی ابری: {e}")
        return False

def delete_trade_by_id(trade_id: str):
    try:
        ws = get_worksheet()
        values = ws.get_all_values()
        if not values or len(values) < 2:
            return False
        headers = values[0]
        if "Trade ID" not in headers:
            return False
        t_idx = headers.index("Trade ID")
        for r_idx, row in enumerate(values[1:], start=2):
            if len(row) > t_idx and str(row[t_idx]).strip() == trade_id.strip():
                ws.delete_rows(r_idx)
                st.cache_data.clear()
                return True
        return False
    except Exception as e:
        st.error(f"خطا در حذف معامله: {e}")
        return False

# =========================================================
# HELPER FUNCTIONS
# =========================================================
def get_index_by_val(d, target_val, default=0):
    if not target_val or pd.isna(target_val) or target_val == "-- انتخاب نشده --":
        return default
    for idx, (k, v) in enumerate(d.items()):
        val_text = v[0] if isinstance(v, tuple) else v
        if str(val_text).strip() == str(target_val).strip():
            return idx
    return default

# =========================================================
# TABS SETUP
# =========================================================
tab1, tab2, tab3 = st.tabs(
    [
        "🎯 آنالیز و ثبت موقعیت",
        "📝 مدیریت و خروج پوزیشن",
        "📊 داشبورد و آمار پیشرفته",
    ]
)

# =========================================================
# TAB 1: ADD / EDIT ANALYSIS & TRADE
# =========================================================
with tab1:
    st.markdown("### 🎯 آنالیز پیشرفته زون و ستاپ معاملاتی (استاندارد ۱۰۰ امتیازی)")
    st.caption("بررسی چک‌لیست چندزمانه ورود، مدیریت ریسک و ارزیابی اعتبار")

    if "current_trade_id" not in st.session_state:
        st.session_state["current_trade_id"] = generate_trade_id()

    if "reset_to_new" in st.session_state and st.session_state["reset_to_new"]:
        st.session_state["draft_selector"] = "-- ایجاد تحلیل جدید --"
        st.session_state["reset_to_new"] = False

    df_all = load_data()
    loaded_data = {}

    if not df_all.empty and "Vaziyat" in df_all.columns:
        draft_trades = df_all[df_all["Vaziyat"] == "Pishnevis (Draft)"].copy()
        if not draft_trades.empty:
            with st.container(border=True):
                st.markdown("##### 📌 بازیابی پیش‌نویس‌های نیمه‌کاره")

                col_filt_sym, col_sort_score = st.columns(2)
                with col_filt_sym:
                    unique_symbols = sorted(
                        [s for s in draft_trades["Namad"].dropna().unique().tolist() if str(s).strip() != ""]
                    )
                    sym_filter_options = ["همه نمادها"] + unique_symbols
                    selected_sym_filter = st.selectbox("🔍 فیلتر بر اساس نماد:", sym_filter_options)

                with col_sort_score:
                    sort_order_options = ["جدیدترین (پیش‌فرض)", "بیشترین امتیاز و گرید به کمترین", "کمترین امتیاز به بیشترین"]
                    selected_sort_order = st.selectbox("📊 مرتب‌سازی بر اساس امتیاز و اعتبار:", sort_order_options)

                filtered_drafts = draft_trades.copy()
                if selected_sym_filter != "همه نمادها":
                    filtered_drafts = filtered_drafts[filtered_drafts["Namad"] == selected_sym_filter]

                if "Emtiyaze 3 Marhale" in filtered_drafts.columns:
                    filtered_drafts["temp_score"] = pd.to_numeric(filtered_drafts["Emtiyaze 3 Marhale"], errors="coerce").fillna(0)
                else:
                    filtered_drafts["temp_score"] = 0

                def get_grade_weight(g):
                    g_str = str(g)
                    if "A+" in g_str:
                        return 3
                    elif "مشروط" in g_str or "B" in g_str:
                        return 2
                    elif "ممنوع" in g_str or "No Trade" in g_str:
                        return 1
                    return 0

                if "Grade" in filtered_drafts.columns:
                    filtered_drafts["grade_weight"] = filtered_drafts["Grade"].apply(get_grade_weight)
                else:
                    filtered_drafts["grade_weight"] = 0

                if selected_sort_order == "بیشترین امتیاز و گرید به کمترین":
                    filtered_drafts = filtered_drafts.sort_values(by=["grade_weight", "temp_score"], ascending=[False, False])
                elif selected_sort_order == "کمترین امتیاز به بیشترین":
                    filtered_drafts = filtered_drafts.sort_values(by=["grade_weight", "temp_score"], ascending=[True, True])

                draft_dict = {
                    f"شناسه: {row.get('Trade ID', '')} | نماد: {row.get('Namad', '')} | گرید: {row.get('Grade', 'پیش‌نویس')} | امتیاز: {row.get('Emtiyaze 3 Marhale', '0')} | جهت: {row.get('Jahat (Buy/Sell)', '')}": row.get('Trade ID')
                    for _, row in filtered_drafts.iterrows()
                }
                draft_options = ["-- ایجاد تحلیل جدید --"] + list(draft_dict.keys())
                
                if st.session_state.get("draft_selector") not in draft_options:
                    st.session_state["draft_selector"] = "-- ایجاد تحلیل جدید --"

                col_sel_draft, col_del_draft = st.columns([4, 1])
                with col_sel_draft:
                    selected_draft_label = st.selectbox(
                        "انتخاب پیش‌نویس جهت بارگذاری و ادامه:",
                        draft_options,
                        key="draft_selector"
                    )
                
                with col_del_draft:
                    st.write("")
                    st.write("")
                    if selected_draft_label != "-- ایجاد تحلیل جدید --":
                        if st.button("🗑️ حذف پیش‌نویس", use_container_width=True):
                            t_id = draft_dict[selected_draft_label]
                            delete_trade_by_id(t_id)
                            st.session_state["current_trade_id"] = generate_trade_id()
                            st.session_state["reset_to_new"] = True
                            st.success(f"پیش‌نویس {t_id} حذف شد.")
                            st.rerun()

                if selected_draft_label != "-- ایجاد تحلیل جدید --":
                    chosen_id = draft_dict[selected_draft_label]
                    matched_rows = df_all[df_all["Trade ID"] == chosen_id]
                    if not matched_rows.empty:
                        loaded_data = matched_rows.iloc[0].to_dict()
                        st.session_state["current_trade_id"] = chosen_id
                else:
                    if st.session_state.get("current_trade_id") in draft_dict.values():
                        st.session_state["current_trade_id"] = generate_trade_id()
                        st.rerun()

    trade_id_val = st.session_state["current_trade_id"]

    with st.container(border=True):
        st.markdown("##### 📌 مشخصات پایه ستاپ")
        col_id, col_sym, col_dir = st.columns(3)
        with col_id:
            st.text_input("شناسه یکتا (Trade ID):", value=trade_id_val, disabled=True, key=f"tid_{trade_id_val}")
        with col_sym:
            default_symbols = ["EURUSD", "XAUUSD", "BTCUSD", "IRTTR", "مظنه آبشده"]
            saved_symbol = str(loaded_data.get("Namad", "")).strip() if pd.notna(loaded_data.get("Namad")) else ""
            
            custom_option_label = "✏️ نماد دلخواه (سایر)..."
            symbol_options = default_symbols + [custom_option_label]

            if saved_symbol in default_symbols:
                sym_box_index = default_symbols.index(saved_symbol)
            else:
                sym_box_index = len(symbol_options) - 1

            chosen_symbol_select = st.selectbox(
                "نماد معاملاتی (Symbol):",
                options=symbol_options,
                index=sym_box_index,
                key=f"sym_select_{trade_id_val}"
            )

            if chosen_symbol_select == custom_option_label:
                custom_initial = saved_symbol if saved_symbol not in default_symbols else ""
                symbol = st.text_input(
                    "تایپ نماد معاملاتی دلخواه:",
                    value=custom_initial,
                    placeholder="مثلاً USDJPY, ETHUSD...",
                    key=f"sym_custom_{trade_id_val}"
                ).strip().upper()
            else:
                symbol = chosen_symbol_select

        with col_dir:
            direction_options = ["-- انتخاب نشده --", "🟢 خرید (Buy / Demand)", "🔴 فروش (Sell / Supply)"]
            default_dir_idx = 0
            if loaded_data.get("Jahat (Buy/Sell)") in direction_options:
                default_dir_idx = direction_options.index(loaded_data.get("Jahat (Buy/Sell)"))
            trade_direction = st.selectbox("جهت معامله روی ناحیه:", direction_options, index=default_dir_idx, key=f"dir_{trade_id_val}")

        # فیلد لینک عکس بخش تحلیل
        analysis_image_url = st.text_input(
            "🔗 لینک تصویر تحلیل چارت:",
            value=str(loaded_data.get("Link Tasvir Tahlil", "")),
            placeholder="مثلاً لینک TradingView یا آدرس تصویر آپلود شده...",
            key=f"img_analysis_{trade_id_val}"
        )

    # ---------------------------------------------------------
    # مرحله ۱: بیس / زون
    # ---------------------------------------------------------
    with st.container(border=True):
        st.subheader("🛡️ مرحله ۱: چند سناریوی اصلی بیس / زون (حداکثر ۳۰ امتیاز)")
        scenario_options = {
            "0": ("-- انتخاب نشده --", "NONE"),
            "1": ("بیس سریع (RBR / DBD / RBD / DBR)", "DIRECT_BASE"),
            "2": ("فلیپ زون یا بیس پنهان در گذشته (Historical)", "FLIP_ZONE"),
            "3": ("کندل منشأ شکست (BOS / CHoCH / OrderBlock)", "CANDLE_OB"),
        }
        zone_tf_options = {
            "0": "-- انتخاب نشده --", "1": "ماهانه (1M)", "2": "هفتگی (1W)",
            "3": "سه روزه (3D)", "4": "روزانه (1D)", "5": "۱۲ ساعته (12H)",
            "6": "۸ ساعته (8H)", "7": "۶ ساعته (6H)", "8": "۴ ساعته (4H)",
            "9": "۳ ساعته (3H)", "10": "۲ ساعته (2H)", "11": "۱ ساعته (1H)",
            "12": "۴۵ دقیقه (45M)", "13": "۳۰ دقیقه (30M)", "14": "۲۰ دقیقه (20M)",
            "15": "۱۵ دقیقه (15M)", "16": "۱۰ دقیقه (10M)", "17": "۵ دقیقه (5M)",
            "18": "۳ دقیقه (3M)", "19": "۲ دقیقه (2M)"
        }

        col_scen, col_ztf, col_date, col_time = st.columns(4)
        with col_scen:
            scen_default_idx = get_index_by_val(scenario_options, loaded_data.get("Senarioye Asli Zone"))
            selected_scenario_key = st.selectbox(
                "مبدأ اصلی Zone از چه نوعی است؟",
                options=list(scenario_options.keys()),
                index=scen_default_idx,
                format_func=lambda x: f"[{x}] {scenario_options[x][0]}" if x != "0" else scenario_options[x][0],
                key=f"scen_{trade_id_val}"
            )
        with col_ztf:
            ztf_default_idx = get_index_by_val(zone_tf_options, loaded_data.get("Timeframe Candle/Zone"))
            selected_zone_tf_key = st.selectbox(
                "تایم‌فریم کندل / ناحیه:",
                options=list(zone_tf_options.keys()),
                index=ztf_default_idx,
                format_func=lambda x: zone_tf_options[x],
                key=f"ztf_{trade_id_val}"
            )
        with col_date:
            saved_date = datetime.date.today()
            if loaded_data.get("Tarikh Candle/Zone"):
                try:
                    saved_date = datetime.datetime.strptime(str(loaded_data.get("Tarikh Candle/Zone")), "%Y-%m-%d").date()
                except Exception:
                    pass
            candle_date = st.date_input("تاریخ کندل / ناحیه:", value=saved_date, key=f"cdate_{trade_id_val}")
        with col_time:
            saved_time = datetime.datetime.now().time()
            if loaded_data.get("Saate Candle/Zone"):
                try:
                    saved_time = datetime.datetime.strptime(str(loaded_data.get("Saate Candle/Zone")), "%H:%M").time()
                except Exception:
                    pass
            
            time_choices = [
                datetime.time(h, m)
                for h in range(24)
                for m in range(0, 60, 5)
            ]
            if saved_time.replace(second=0, microsecond=0) not in time_choices:
                time_choices.append(saved_time.replace(second=0, microsecond=0))
                time_choices = sorted(time_choices)
                
            default_t_idx = time_choices.index(saved_time.replace(second=0, microsecond=0))
            candle_time = st.selectbox(
                "ساعت کندل / ناحیه:",
                options=time_choices,
                index=default_t_idx,
                format_func=lambda t: t.strftime("%H:%M"),
                key=f"ctime_{trade_id_val}"
            )

        scenario_info = scenario_options[selected_scenario_key]
        scenario_code = scenario_info[1]
        zone_timeframe_val = zone_tf_options[selected_zone_tf_key]

        score_m1 = 0
        details = {
            "Trade ID": trade_id_val,
            "Tarikh": loaded_data.get("Tarikh", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
            "Namad": symbol,
            "Jahat (Buy/Sell)": trade_direction,
            "Link Tasvir Tahlil": analysis_image_url,
            "Senarioye Asli Zone": scenario_info[0],
            "Timeframe Candle/Zone": zone_timeframe_val,
            "Tarikh Candle/Zone": str(candle_date),
            "Saate Candle/Zone": candle_time.strftime("%H:%M"),
        }

        if scenario_code != "NONE":
            st.markdown("---")
            col_s1, col_s2 = st.columns(2)

            if scenario_code == "DIRECT_BASE":
                with col_s1:
                    patt_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("RBR یا DBD (ادامه‌دهنده)", 4), "2": ("RBD یا DBR (بازگشتی)", 4)}
                    patt_sel = st.selectbox("۱.۱. نوع الگوی بیس؟", list(patt_opts.keys()), index=get_index_by_val(patt_opts, loaded_data.get("1.1 Olgooye Base")), format_func=lambda x: patt_opts[x][0], key=f"patt_{trade_id_val}")
                    score_m1 += patt_opts[patt_sel][1]
                    details["1.1 Olgooye Base"] = patt_opts[patt_sel][0]

                    fresh_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("🛡️ کاملاً تازه و تست‌نشده (Fresh)", 5), "2": ("یک‌بار تست‌شده همراه با واکنش", 2), "3": ("تست‌شده و کهنه", 0)}
                    fresh_sel = st.selectbox("۱.۲. وضعیت دست‌نخوردگی (Freshness)؟", list(fresh_opts.keys()), index=get_index_by_val(fresh_opts, loaded_data.get("1.2 Freshness Base")), format_func=lambda x: fresh_opts[x][0], key=f"fresh_{trade_id_val}")
                    score_m1 += fresh_opts[fresh_sel][1]
                    details["1.2 Freshness Base"] = fresh_opts[fresh_sel][0]

                    count_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("۱ تا ۳ کندل (قوی)", 4), "2": ("۳ تا ۵ کندل (متوسط)", 2), "3": ("بیشتر از ۵ کندل (ضعیف)", 0)}
                    count_sel = st.selectbox("۱.۳. تعداد کندل‌های داخل بیس؟", list(count_opts.keys()), index=get_index_by_val(count_opts, loaded_data.get("1.3 Tedad Candle Base")), format_func=lambda x: count_opts[x][0], key=f"cnt_{trade_id_val}")
                    score_m1 += count_opts[count_sel][1]
                    details["1.3 Tedad Candle Base"] = count_opts[count_sel][0]

                    type_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("دوجی / فشرده و منشأ بیس (Origin)", 4), "2": ("ماروبوزو یا بیس میانی", 2)}
                    type_sel = st.selectbox("۱.۴. شکل کندل‌های بیس و جایگاه آن؟", list(type_opts.keys()), index=get_index_by_val(type_opts, loaded_data.get("1.4 Shekl va Jaygahe Base")), format_func=lambda x: type_opts[x][0], key=f"typ_{trade_id_val}")
                    score_m1 += type_opts[type_sel][1]
                    details["1.4 Shekl va Jaygahe Base"] = type_opts[type_sel][0]

                with col_s2:
                    dep_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("⚡ بدنه بلند و کلوز نزدیک + FVG + ۲ کندل ادامه‌دار", 5), "2": ("بدنه متوسط یا FVG ضعیف", 2), "3": ("خروج ضعیف و کم‌رمق", 0)}
                    dep_sel = st.selectbox("۱.۵. خروج از بیس (Departure Body & FVG)؟", list(dep_opts.keys()), index=get_index_by_val(dep_opts, loaded_data.get("1.5 Khorooje Base (Departure)")), format_func=lambda x: dep_opts[x][0], key=f"dep_{trade_id_val}")
                    score_m1 += dep_opts[dep_sel][1]
                    details["1.5 Khorooje Base (Departure)"] = dep_opts[dep_sel][0]

                    pip_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("حرکت قوی و ادامه‌دار (پرتاب لگ استاندارد)", 3), "2": ("حرکت کم و سریعاً وارد اصلاح شد", 1)}
                    pip_sel = st.selectbox("۱.۶. میزان پرتاب لگ؟", list(pip_opts.keys()), index=get_index_by_val(pip_opts, loaded_data.get("1.6 Mizane Parthabe Lag")), format_func=lambda x: pip_opts[x][0], key=f"pip_{trade_id_val}")
                    score_m1 += pip_opts[pip_sel][1]
                    details["1.6 Mizane Parthabe Lag"] = pip_opts[pip_sel][0]

                    ach_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("🎯 BOS قوی یا حذف زون مقابل (Removal)", 5), "2": ("BOS خرد یا هانت/سوئیپ", 2), "3": ("بدون دستاورد", 0)}
                    ach_sel = st.selectbox("۱.۷. دستاورد بیس (Achievement)؟", list(ach_opts.keys()), index=get_index_by_val(ach_opts, loaded_data.get("1.7 Dastavard Base")), format_func=lambda x: ach_opts[x][0], key=f"ach_{trade_id_val}")
                    score_m1 += ach_opts[ach_sel][1]
                    details["1.7 Dastavard Base"] = ach_opts[ach_sel][0]

            elif scenario_code == "FLIP_ZONE":
                with col_s1:
                    ftype_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("فلیپ زون (سطح تبدیل‌شده)", 5), "2": ("بیس پنهان در گذشته", 3)}
                    ftype_sel = st.selectbox("۱.۱. جنس ناحیه؟", list(ftype_opts.keys()), index=get_index_by_val(ftype_opts, loaded_data.get("1.1 Jense Nahiye")), format_func=lambda x: ftype_opts[x][0], key=f"ftyp_{trade_id_val}")
                    score_m1 += ftype_opts[ftype_sel][1]
                    details["1.1 Jense Nahiye"] = ftype_opts[ftype_sel][0]

                    fresh_flip_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("🛡️ کاملاً تازه و تست‌نشده (Fresh)", 5), "2": ("یک‌بار تست‌شده همراه با واکنش", 2), "3": ("تست‌شده و کهنه", 0)}
                    fresh_flip_sel = st.selectbox("۱.۲. تازگی فلیپ (Freshness)؟", list(fresh_flip_opts.keys()), index=get_index_by_val(fresh_flip_opts, loaded_data.get("1.2 Freshness Flip")), format_func=lambda x: fresh_flip_opts[x][0], key=f"ffresh_{trade_id_val}")
                    score_m1 += fresh_flip_opts[fresh_flip_sel][1]
                    details["1.2 Freshness Flip"] = fresh_flip_opts[fresh_flip_sel][0]

                    fbreak_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("شکست شارپ با ماروبوزو و بدنه بلند", 5), "2": ("شکست ضعیف یا با سایه (Shadow)", 2)}
                    fbreak_sel = st.selectbox("۱.۳. کیفیت شکستی که فلیپ را ساخته؟", list(fbreak_opts.keys()), index=get_index_by_val(fbreak_opts, loaded_data.get("1.3 Keifiyaat Shekaste Flip")), format_func=lambda x: fbreak_opts[x][0], key=f"fbrk_{trade_id_val}")
                    score_m1 += fbreak_opts[fbreak_sel][1]
                    details["1.3 Keifiyaat Shekaste Flip"] = fbreak_opts[fbreak_sel][0]

                with col_s2:
                    frem_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بله، زون مقابل را کاملاً پاک کرده", 5), "2": ("خیر، واکنش ضعیف بوده", 1)}
                    frem_sel = st.selectbox("۱.۴. حذف زون مقابل (Removal)؟", list(frem_opts.keys()), index=get_index_by_val(frem_opts, loaded_data.get("1.4 Removal Zone Moghabel")), format_func=lambda x: frem_opts[x][0], key=f"frem_{trade_id_val}")
                    score_m1 += frem_opts[frem_sel][1]
                    details["1.4 Removal Zone Moghabel"] = frem_opts[frem_sel][0]

                    fsweep_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("⚡ بله، قبل از شکست سوئیپ داشته", 5), "2": ("خیر", 1)}
                    fsweep_sel = st.selectbox("۱.۵. سوئیپ نقدینگی در گذشته این سطح؟", list(fsweep_opts.keys()), index=get_index_by_val(fsweep_opts, loaded_data.get("1.5 Sweep Naghdinegi Sath")), format_func=lambda x: fsweep_opts[x][0], key=f"fswp_{trade_id_val}")
                    score_m1 += fsweep_opts[fsweep_sel][1]
                    details["1.5 Sweep Naghdinegi Sath"] = fsweep_opts[fsweep_sel][0]

                    ffvg_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("FVG واضح و پرنشده وجود دارد", 5), "2": ("FVG وجود ندارد یا پر شده", 1)}
                    ffvg_sel = st.selectbox("۱.۶. وضعیت FVG در محدوده فلیپ؟", list(ffvg_opts.keys()), index=get_index_by_val(ffvg_opts, loaded_data.get("1.6 Vaziyaate FVG Flip")), format_func=lambda x: ffvg_opts[x][0], key=f"ffvg_{trade_id_val}")
                    score_m1 += ffvg_opts[ffvg_sel][1]
                    details["1.6 Vaziyaate FVG Flip"] = ffvg_opts[ffvg_sel][0]

            elif scenario_code == "CANDLE_OB":
                with col_s1:
                    cbreak_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("🎯 BOS ماژور یا CHoCH اصلی", 5), "2": ("BOS اینترنال (خرد)", 2)}
                    cbreak_sel = st.selectbox("۱.۱. نوع شکستی که این کندل ساخته؟", list(cbreak_opts.keys()), index=get_index_by_val(cbreak_opts, loaded_data.get("1.1 Noe Shekaste Candle")), format_func=lambda x: cbreak_opts[x][0], key=f"cbrk_{trade_id_val}")
                    score_m1 += cbreak_opts[cbreak_sel][1]
                    details["1.1 Noe Shekaste Candle"] = cbreak_opts[cbreak_sel][0]

                    fresh_cand_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("🛡️ کاملاً تازه و تست‌نشده (Fresh)", 5), "2": ("یک‌بار تست‌شده همراه با واکنش", 2), "3": ("تست‌شده و کهنه", 0)}
                    fresh_cand_sel = st.selectbox("۱.۲. تازگی کندل منشأ (Freshness)؟", list(fresh_cand_opts.keys()), index=get_index_by_val(fresh_cand_opts, loaded_data.get("1.2 Freshness Candle")), format_func=lambda x: fresh_cand_opts[x][0], key=f"cfresh_{trade_id_val}")
                    score_m1 += fresh_cand_opts[fresh_cand_sel][1]
                    details["1.2 Freshness Candle"] = fresh_cand_opts[fresh_cand_sel][0]

                    csweep_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("⚡ بله، هانت / سوئیپ اکستریم داشته", 5), "2": ("خیر، سوئیپ نداشته", 1)}
                    csweep_sel = st.selectbox("۱.۳. سوئیپ قبل از حرکت؟", list(csweep_opts.keys()), index=get_index_by_val(csweep_opts, loaded_data.get("1.3 Sweep Ghabl Shillik")), format_func=lambda x: csweep_opts[x][0], key=f"cswp_{trade_id_val}")
                    score_m1 += csweep_opts[csweep_sel][1]
                    details["1.3 Sweep Ghabl Shillik"] = csweep_opts[csweep_sel][0]

                with col_s2:
                    cfvg_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("FVG واضح و قوی بلافاصله بعد از کندل", 5), "2": ("بدون FVG", 1)}
                    cfvg_sel = st.selectbox("۱.۴. وضعیت FVG بعد از کندل؟", list(cfvg_opts.keys()), index=get_index_by_val(cfvg_opts, loaded_data.get("1.4 FVG Ba'ad Candle")), format_func=lambda x: cfvg_opts[x][0], key=f"cfvg_{trade_id_val}")
                    score_m1 += cfvg_opts[cfvg_sel][1]
                    details["1.4 FVG Ba'ad Candle"] = cfvg_opts[cfvg_sel][0]

                    cbody_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بدنه کشیده و کلوز نزدیک به سقف/کف", 5), "2": ("کندل با سایه بلند و بدنه کوچک", 2)}
                    cbody_sel = st.selectbox("۱.۵. کیفیت بدنه و کلوز کندل؟", list(cbody_opts.keys()), index=get_index_by_val(cbody_opts, loaded_data.get("1.5 Keifiyaat Body Candle")), format_func=lambda x: cbody_opts[x][0], key=f"cbod_{trade_id_val}")
                    score_m1 += cbody_opts[cbody_sel][1]
                    details["1.5 Keifiyaat Body Candle"] = cbody_opts[cbody_sel][0]

                    cfollow_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("حداقل ۲ کندل قوی و هم‌جهت بعد از آن", 5), "2": ("سریعاً وارد اصلاح شد", 1)}
                    cfollow_sel = st.selectbox("۱.۶. تداوم حرکت (Follow-through)؟", list(cfollow_opts.keys()), index=get_index_by_val(cfollow_opts, loaded_data.get("1.6 Tadaome Harakat Ba'ad Candle")), format_func=lambda x: cfollow_opts[x][0], key=f"cfol_{trade_id_val}")
                    score_m1 += cfollow_opts[cfollow_sel][1]
                    details["1.6 Tadaome Harakat Ba'ad Candle"] = cfollow_opts[cfollow_sel][0]

    # ---------------------------------------------------------
    # مرحله ۲: کانتکست تایم بالا HTF
    # ---------------------------------------------------------
    with st.container(border=True):
        st.subheader("🌐 مرحله ۲: قفل تایم‌فریم و کانتکست تایم بالا HTF (حداکثر ۴۰ امتیاز)")
        tf_options = {
            "0": ("-- انتخاب نشده --", "NONE"),
            "1": ("روزانه (HTF: هفتگی | LTF: ۴ ساعته)", "1D"),
            "2": ("۴ ساعته (HTF: روزانه | LTF: ۱ ساعته)", "4H"),
            "3": ("۱ ساعته (HTF: ۴ ساعته | LTF: ۱۵ دقیقه)", "1H"),
            "4": ("۱۵ دقیقه (HTF: ۱ ساعته | LTF: ۳/۵ دقیقه)", "15M"),
        }

        col_m2_1, col_m2_2 = st.columns(2)
        with col_m2_1:
            tf_default_idx = 0
            loaded_tf = loaded_data.get("Timeframe Zone (MTF)")
            if loaded_tf and pd.notna(loaded_tf):
                for idx, (k, v) in enumerate(tf_options.items()):
                    if v[1] == loaded_tf:
                        tf_default_idx = idx
                        break

            tf_sel = st.selectbox("تایم‌فریم اصلی زون (MTF) را انتخاب کنید:", list(tf_options.keys()), index=tf_default_idx, format_func=lambda x: tf_options[x][0], key=f"tf_{trade_id_val}")
            mtf = tf_options[tf_sel][1]
            details["Timeframe Zone (MTF)"] = mtf

            score_m2 = 0
            htf_bias_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("🟢 بله، کاملاً هم‌جهت با روند تایم بالا (HTF)", 12), "2": ("🔴 خیر، معامله اصلاحی / خلاف روند تایم بالا", 0)}
            htf_bias_sel = st.selectbox("۲.۱. هم‌جهتی با تایم بالا (HTF)؟", list(htf_bias_opts.keys()), index=get_index_by_val(htf_bias_opts, loaded_data.get("2.1 Ham-jehati ba HTF")), format_func=lambda x: htf_bias_opts[x][0], key=f"hbias_{trade_id_val}")
            score_m2 += htf_bias_opts[htf_bias_sel][1]
            details["2.1 Ham-jehati ba HTF"] = htf_bias_opts[htf_bias_sel][0]

            htf_curve_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("کاملاً مناسب و فاصله کافی (حداقل R:R ۱ به ۲)", 10), "2": ("نزدیک به زون مقابل تایم بالا (پرریسک)", 0)}
            htf_curve_sel = st.selectbox("۲.۲. موقعیت زون روی منحنی و فاصله تا مانع HTF؟", list(htf_curve_opts.keys()), index=get_index_by_val(htf_curve_opts, loaded_data.get("2.2 Mogheiyat rooye Curve")), format_func=lambda x: htf_curve_opts[x][0], key=f"hcurv_{trade_id_val}")
            score_m2 += htf_curve_opts[htf_curve_sel][1]
            details["2.2 Mogheiyat rooye Curve"] = htf_curve_opts[htf_curve_sel][0]

        with col_m2_2:
            htf_power_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("لگ‌های موافق قوی و اصلاح‌ها کوتاه/ضعیف", 10), "2": ("اصلاح‌ها عمیق و حرکت در حال ضعیف شدن", 3)}
            htf_power_sel = st.selectbox("۲.۳. موازنه قدرت و مقایسه لگ‌ها و کندل‌ها؟", list(htf_power_opts.keys()), index=get_index_by_val(htf_power_opts, loaded_data.get("2.3 Movazene Ghodrat Lag-ha")), format_func=lambda x: htf_power_opts[x][0], key=f"hpow_{trade_id_val}")
            score_m2 += htf_power_opts[htf_power_sel][1]
            details["2.3 Movazene Ghodrat Lag-ha"] = htf_power_opts[htf_power_sel][0]

            htf_struct_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("رونددار و با گام‌های حرکتی قوی (Trending)", 8), "2": ("در محدوده فشرده و رنج (Ranging)", 2)}
            htf_struct_sel = st.selectbox("۲.۴. وضعیت حرکت تایم بالا (Trend/Range)؟", list(htf_struct_opts.keys()), index=get_index_by_val(htf_struct_opts, loaded_data.get("2.4 Vaziyaat HTF (Trend/Range)")), format_func=lambda x: htf_struct_opts[x][0], key=f"hstr_{trade_id_val}")
            score_m2 += htf_struct_opts[htf_struct_sel][1]
            details["2.4 Vaziyaat HTF (Trend/Range)"] = htf_struct_opts[htf_struct_sel][0]

    # ---------------------------------------------------------
    # مرحله ۳: اپروچ
    # ---------------------------------------------------------
    with st.container(border=True):
        st.subheader("⚡ مرحله ۳: نحوه رسیدن قیمت به ناحیه (حداکثر ۳۰ امتیاز)")
        col_m3_1, col_m3_2 = st.columns(2)
        score_m3 = 0

        with col_m3_1:
            app_type_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("فشرده / اصلاحی (Compression)", 12), "2": ("حرکت معمولی", 6), "3": ("اسپایک / شارپ و پرفشار", 0)}
            app_type_sel = st.selectbox("۳.۱. نحوه رسیدن قیمت به زون؟", list(app_type_opts.keys()), index=get_index_by_val(app_type_opts, loaded_data.get("3.1 Nahveye Rasidan (Approach)")), format_func=lambda x: app_type_opts[x][0], key=f"apptyp_{trade_id_val}")
            score_m3 += app_type_opts[app_type_sel][1]
            details["3.1 Nahveye Rasidan (Approach)"] = app_type_opts[app_type_sel][0]

            app_liq_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("⚡ ایندیوسمنت ساخته شده یا قبل از زون سوئیپ انجام شده", 10), "2": ("بدون سوئیپ و ایندیوسمنت", 2)}
            app_liq_sel = st.selectbox("۳.۲. نقدینگی قبل از رسیدن (Inducement/Sweep)؟", list(app_liq_opts.keys()), index=get_index_by_val(app_liq_opts, loaded_data.get("3.2 Naghdinegi Ghabl Zone")), format_func=lambda x: app_liq_opts[x][0], key=f"appliq_{trade_id_val}")
            score_m3 += app_liq_opts[app_liq_sel][1]
            details["3.2 Naghdinegi Ghabl Zone"] = app_liq_opts[app_liq_sel][0]

        with col_m3_2:
            app_mom_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("کندل‌ها در حال تضعیف و کاهش اندازه بدنه", 8), "2": ("ورود با کندل‌های پرقدرت و بدنه بلند", 1)}
            app_mom_sel = st.selectbox("۳.۳. مومنتوم و بدنه کندل‌ها نزدیک به زون؟", list(app_mom_opts.keys()), index=get_index_by_val(app_mom_opts, loaded_data.get("3.3 Momentum Nazdik Zone")), format_func=lambda x: app_mom_opts[x][0], key=f"appmom_{trade_id_val}")
            score_m3 += app_mom_opts[app_mom_sel][1]
            details["3.3 Momentum Nazdik Zone"] = app_mom_opts[app_mom_sel][0]

    # ارزیابی تجمیعی ۳ مرحله
    total_score_3m = score_m1 + score_m2 + score_m3

    grade = ""
    risk_pct = 0.0
    action = ""
    show_m4 = False
    can_proceed = False

    with st.container(border=True):
        st.markdown("##### 🏁 وضعیت و رتبه‌بندی اولیه")
        col_res1, col_res2 = st.columns([1, 2])
        with col_res1:
            st.metric("امتیاز ۳ مرحله اولیه", f"{total_score_3m} / 100")
        with col_res2:
            if total_score_3m >= 80:
                grade = "A+ (عالی - Set & Forget)"
                risk_pct = 1.0
                action = "ورود مستقیم با لیمیت مجاز است (کیفیت ستاپ فوق‌العاده)."
                st.markdown(f'<div class="badge-grade badge-aplus">GRADE: {grade} | RISK: {risk_pct}%</div>', unsafe_allow_html=True)
                st.success(f"✅ {action}")
                can_proceed = True
            elif total_score_3m < 60:
                grade = "معامله ممنوع (No Trade)"
                risk_pct = 0.0
                action = "معامله لغو شد (امتیاز ۳ مرحله اول کمتر از ۶۰ است)."
                st.markdown(f'<div class="badge-grade badge-notrade">GRADE: {grade}</div>', unsafe_allow_html=True)
                st.error(f"⛔ {action}")
                can_proceed = False
            else:
                grade = "مشروط به تأییدیه LTF"
                st.markdown(f'<div class="badge-grade badge-b">GRADE: نیاز به ارزیابی مرحله ۴</div>', unsafe_allow_html=True)
                st.warning("⚠️ امتیاز بین ۶۰ تا ۷۹ است. برای صدور مجوز ورود، باید در مرحله ۴ حداقل ۳۰ امتیاز از ۵۰ را کسب نمایید.")
                show_m4 = True

    # ---------------------------------------------------------
    # مرحله ۴: تأییدیه تایم پایین LTF
    # ---------------------------------------------------------
    score_m4 = 0
    if show_m4:
        with st.container(border=True):
            st.subheader("🔍 مرحله ۴: تأییدیه ورود در تایم پایین (LTF) و تایم زون (حداکثر ۵۰ امتیاز)")
            col_m4_1, col_m4_2 = st.columns(2)

            with col_m4_1:
                ltf_str_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("🎯 شکست با کلوز بدنه (BOS / MSS / CHoCH)", 12), "2": ("شکست صرفاً با سایه (Wick)", 5), "3": ("بدون شکست ساختار", 0)}
                ltf_str_sel = st.selectbox("۴.۱. شکست ساختار در تایم پایین (LTF)؟", list(ltf_str_opts.keys()), index=get_index_by_val(ltf_str_opts, loaded_data.get("4.1 Shekaste Sakhtar LTF")), format_func=lambda x: ltf_str_opts[x][0], key=f"ltfstr_{trade_id_val}")
                score_m4 += ltf_str_opts[ltf_str_sel][1]
                details["4.1 Shekaste Sakhtar LTF"] = ltf_str_opts[ltf_str_sel][0]

                zone_patt_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("اینگلف / پوشای قدرتمند (Engulfing)", 8), "2": ("پین‌بار / چکش / شوتینگ استار", 8), "3": ("ستاره صبحگاهی / عصرگاهی", 6), "4": ("سایر الگوها", 4), "5": ("خیر", 0)}
                zone_patt_sel = st.selectbox("۴.۲. وضعیت الگوی کندلی تایم زون؟", list(zone_patt_opts.keys()), index=get_index_by_val(zone_patt_opts, loaded_data.get("4.2 Olgooye Candli Zone")), format_func=lambda x: zone_patt_opts[x][0], key=f"zpatt_{trade_id_val}")
                score_m4 += zone_patt_opts[zone_patt_sel][1]
                details["4.2 Olgooye Candli Zone"] = zone_patt_opts[zone_patt_sel][0]

                ltf_disp_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("⚡ جابه‌جایی پرقدرت (Displacement) + FVG واضح", 8), "2": ("بدون FVG / ضعیف", 1)}
                ltf_disp_sel = st.selectbox("۴.۳. وضعیت جابه‌جایی و FVG در تایم پایین؟", list(ltf_disp_opts.keys()), index=get_index_by_val(ltf_disp_opts, loaded_data.get("4.3 Displacement va FVG LTF")), format_func=lambda x: ltf_disp_opts[x][0], key=f"ltfdisp_{trade_id_val}")
                score_m4 += ltf_disp_opts[ltf_disp_sel][1]
                details["4.3 Displacement va FVG LTF"] = ltf_disp_opts[ltf_disp_sel][0]

            with col_m4_2:
                ltf_candle_power_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بله، بدنه قوی‌تر و شادوها کوتاه‌تر (تسلط کامل)", 6), "2": ("متوسط", 3), "3": ("خیر، شادوها بلند", 0)}
                ltf_candle_power_sel = st.selectbox("۴.۴. تسلط کندل‌های موافق در LTF؟", list(ltf_candle_power_opts.keys()), index=get_index_by_val(ltf_candle_power_opts, loaded_data.get("4.4 Ghodrate Candle-haye Movafagh LTF")), format_func=lambda x: ltf_candle_power_opts[x][0], key=f"ltfcand_{trade_id_val}")
                score_m4 += ltf_candle_power_opts[ltf_candle_power_sel][1]
                details["4.4 Ghodrate Candle-haye Movafagh LTF"] = ltf_candle_power_opts[ltf_candle_power_sel][0]

                ltf_lag_power_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("لگ‌های موافق قوی و پرشتاب‌تر", 6), "2": ("موازنه یکسان", 3), "3": ("لگ‌های موافق ضعیف‌تر", 0)}
                ltf_lag_power_sel = st.selectbox("۴.۵. وضعیت لگ‌های موافق در LTF؟", list(ltf_lag_power_opts.keys()), index=get_index_by_val(ltf_lag_power_opts, loaded_data.get("4.5 Vaziyate Lag-haye Movafagh LTF")), format_func=lambda x: ltf_lag_power_opts[x][0], key=f"ltflag_{trade_id_val}")
                score_m4 += ltf_lag_power_opts[ltf_lag_power_sel][1]
                details["4.5 Vaziyate Lag-haye Movafagh LTF"] = ltf_lag_power_opts[ltf_lag_power_sel][0]

                ltf_touch_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("برخورد و حرکت سریع (Touch & Go)", 5), "2": ("معطلی طولانی داخل زون", 1)}
                ltf_touch_sel = st.selectbox("۴.۶. رفتار قیمت داخل زون؟", list(ltf_touch_opts.keys()), index=get_index_by_val(ltf_touch_opts, loaded_data.get("4.6 Raftare Ghemat Daron Zone")), format_func=lambda x: ltf_touch_opts[x][0], key=f"ltftch_{trade_id_val}")
                score_m4 += ltf_touch_opts[ltf_touch_sel][1]
                details["4.6 Raftare Ghemat Daron Zone"] = ltf_touch_opts[ltf_touch_sel][0]

                ltf_sess_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("سشن اصلی (لندن / نیویورک / هم‌پوشانی)", 5), "2": ("خارج از سشن اصلی", 1)}
                ltf_sess_sel = st.selectbox("۴.۷. سشن معاملاتی؟", list(ltf_sess_opts.keys()), index=get_index_by_val(ltf_sess_opts, loaded_data.get("4.7 Session Moamelati")), format_func=lambda x: ltf_sess_opts[x][0], key=f"ltfsess_{trade_id_val}")
                score_m4 += ltf_sess_opts[ltf_sess_sel][1]
                details["4.7 Session Moamelati"] = ltf_sess_opts[ltf_sess_sel][0]

            st.metric("امتیاز کسب‌شده از تأییدیه مرحله ۴", f"{score_m4} / 50")

            if score_m4 >= 30:
                grade = "B (خوب - با تأییدیه)"
                risk_pct = 0.65
                action = "مجوز ورود با ریسک کنترل‌شده صادر شد."
                st.markdown(f'<div class="badge-grade badge-b">GRADE: {grade} | RISK: {risk_pct}%</div>', unsafe_allow_html=True)
                st.success(f"✅ {action}")
                can_proceed = True
            else:
                grade = "معامله ممنوع (تأییدیه ناموفق)"
                risk_pct = 0.0
                action = "امتیاز تأییدیه به حد نصاب ۳۰ نرسید."
                st.markdown(f'<div class="badge-grade badge-notrade">GRADE: {grade}</div>', unsafe_allow_html=True)
                st.error(f"⛔ {action}")
                can_proceed = False

    # ---------------------------------------------------------
    # ثبت پیش‌نویس
    # ---------------------------------------------------------
    with st.container(border=True):
        col_draft, _ = st.columns([1, 1])
        with col_draft:
            if st.button("💾 ذخیره به عنوان پیش‌نویس (Draft)", use_container_width=True):
                if not symbol:
                    st.error("❌ لطفاً ابتدا نماد معاملاتی را مشخص کنید.")
                else:
                    details["Balance"] = loaded_data.get("Balance", "")
                    details["Emtiyaze 3 Marhale"] = total_score_3m
                    details["Grade"] = grade if grade else "Pishnevis"
                    details["Darsade Risk"] = f"{risk_pct}%"
                    details["Risk ($)"] = ""
                    details["Hajm (Lot)"] = ""
                    details["Vaziyat"] = "Pishnevis (Draft)"
                    details["Noe TP / Khorooj"] = "Dar Hale Tahlil"
                    details["Natijeh (PnL $)"] = ""
                    details["R:R Vaghei"] = ""

                    if upsert_trade(details):
                        st.session_state["current_trade_id"] = generate_trade_id()
                        st.session_state["reset_to_new"] = True
                        st.success(f"پیش‌نویس {trade_id_val} با موفقیت ذخیره شد.")
                        st.rerun()

    # ---------------------------------------------------------
    # مدیریت پیشرفته حجم و ریسک (پشتیبانی کامل از فارکس، کریپتو، طلا و ارز مبنا)
    # ---------------------------------------------------------
    if can_proceed:
        with st.container(border=True):
            st.subheader("💰 محاسبه ریسک، حجم و مدیریت پوزیشن")

            # ۱. انتخاب دستی بازار و واحدها
            col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
            with col_cfg1:
                market_type = st.selectbox(
                    "بازار معاملاتی:",
                    [
                        "فارکس ماژور و طلا جهانی (Pip & Lot)",
                        "کریپتو بر پایه تتر (BTC, ETH / USDT)",
                        "تتر به تومان (USDT / IRT)",
                        "طلای ۱۸ عیار و آبشده (Toman)",
                        "فارکس کراس / معکوس (USDJPY, USDCHF, ...)"
                    ],
                    key=f"mkt_type_{trade_id_val}"
                )

            with col_cfg2:
                wallet_currency = st.selectbox(
                    "واحد پولی حساب (کیف‌پول):",
                    ["تتر (USDT)", "تومان", "دلار ($)"],
                    key=f"wallet_curr_{trade_id_val}"
                )

            with col_cfg3:
                if "فارکس" in market_type:
                    target_vol_unit = "Lot"
                elif "کریپتو" in market_type:
                    target_vol_unit = f"واحد ({symbol if symbol else 'Coin'})"
                elif "تتر به تومان" in market_type:
                    target_vol_unit = "تتر (USDT)"
                else:
                    target_vol_unit = st.selectbox("واحد سفارش طلا:", ["گرم", "مثقال"], key=f"gold_u_{trade_id_val}")
                
                st.text_input("واحد حجم سفارش (خروجی):", value=target_vol_unit, disabled=True, key=f"disp_u_{trade_id_val}")

            # ۲. دریافت بالانس و درصد ریسک
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                raw_balance = loaded_data.get("Balance", "")
                try:
                    default_b = float(raw_balance) if raw_balance != "" and pd.notna(raw_balance) else (100.0 if wallet_currency != "تومان" else 10000000.0)
                except (ValueError, TypeError):
                    default_b = 100.0 if wallet_currency != "تومان" else 10000000.0

                balance = st.number_input(
                    f"موجودی حساب ({wallet_currency}):",
                    min_value=0.01,
                    value=default_b,
                    step=10.0 if wallet_currency != "تومان" else 500000.0,
                    key=f"bal_in_{trade_id_val}"
                )

            with col_b2:
                actual_risk_pct = st.number_input(
                    "درصد ریسک روی بالانس (%):",
                    min_value=0.01,
                    max_value=100.0,
                    value=float(risk_pct) if risk_pct > 0 else 1.0,
                    step=0.1,
                    format="%.2f",
                    key=f"risk_in_{trade_id_val}"
                )

            # مقدار سرمایه در ریسک بر مبنای کیف‌پول
            risk_wallet = float(balance) * (float(actual_risk_pct) / 100.0)
            pos_size = 0.0
            pos_value = 0.0
            pos_value_unit = wallet_currency

            # ۳. شاخه اول: فارکس ماژور استاندارد
            if market_type == "فارکس ماژور و طلا جهانی (Pip & Lot)":
                col_fx1, col_fx2 = st.columns(2)
                with col_fx1:
                    sl_pips = st.number_input("فاصله تا حد ضرر (Pip / Point):", min_value=0.1, value=15.0, step=1.0, key=f"fx_sl_{trade_id_val}")
                with col_fx2:
                    pip_val = st.number_input(f"ارزش هر پیپ برای ۱ لات ({wallet_currency}):", min_value=0.01, value=10.0, step=0.5, key=f"fx_pv_{trade_id_val}")

                if sl_pips > 0 and pip_val > 0:
                    pos_size = risk_wallet / (float(sl_pips) * float(pip_val))
                
                pos_value = pos_size * 100000.0
                pos_value_unit = "ارز پایه (Notional)"

            # شاخه دوم: فارکس کراس یا معکوس
            elif market_type == "فارکس کراس / معکوس (USDJPY, USDCHF, ...)":
                col_cr1, col_cr2, col_cr3 = st.columns(3)
                with col_cr1:
                    sl_pips = st.number_input("فاصله تا حد ضرر (Pip):", min_value=0.1, value=20.0, step=1.0, key=f"cr_sl_{trade_id_val}")
                with col_cr2:
                    cross_rate = st.number_input("نرخ لحظه‌ای جفت‌ارز (جهت تبدیل پیپ):", min_value=0.0001, value=150.00, format="%.4f", key=f"cr_rate_{trade_id_val}")
                with col_cr3:
                    base_pip_standard = st.number_input("پیپ مبنای ارز مظنه (معمولاً ۱۰۰۰ برای ین، ۱۰ برای سایرین):", min_value=0.1, value=1000.0 if "JPY" in symbol.upper() else 10.0, key=f"cr_bp_{trade_id_val}")

                effective_pip_value = (base_pip_standard / cross_rate) if cross_rate > 0 else 0.0
                if sl_pips > 0 and effective_pip_value > 0:
                    pos_size = risk_wallet / (float(sl_pips) * effective_pip_value)
                pos_value = pos_size * 100000.0
                pos_value_unit = "ارز پایه"

            # شاخه سوم: کریپتو، تتر، طلا
            else:
                col_p_e1, col_p_e2 = st.columns(2)
                with col_p_e1:
                    entry_p = st.number_input(
                        "قیمت ورود (Entry):",
                        min_value=0.000001,
                        value=100000.0 if "تومان" in market_type or "تومان" in wallet_currency else 65000.0,
                        format="%.4f",
                        key=f"pe_ent_{trade_id_val}"
                    )
                with col_p_e2:
                    sl_p = st.number_input(
                        "قیمت حد ضرر (Stop Loss):",
                        min_value=0.000001,
                        value=90000.0 if "تومان" in market_type or "تومان" in wallet_currency else 63500.0,
                        format="%.4f",
                        key=f"pe_sl_{trade_id_val}"
                    )

                price_distance = abs(float(entry_p) - float(sl_p))

                usdt_to_irt_rate = 1.0
                needs_conversion = False
                
                if "کریپتو" in market_type and wallet_currency == "تومان":
                    needs_conversion = True
                    usdt_to_irt_rate = st.number_input("نرخ روز تبدیل تتر به تومان:", min_value=1.0, value=100000.0, step=500.0, key=f"conv_irt_{trade_id_val}")
                
                elif ("تومان" in market_type or "طلا" in market_type) and wallet_currency in ["تتر (USDT)", "دلار ($)"]:
                    needs_conversion = True
                    default_rate = float(entry_p) if "تتر به تومان" in market_type else 100000.0
                    usdt_to_irt_rate = st.number_input("نرخ تبدیل تتر به تومان:", min_value=1.0, value=default_rate, step=500.0, key=f"conv_usdt_{trade_id_val}")

                if price_distance > 0:
                    if "کریپتو" in market_type and wallet_currency == "تومان":
                        risk_in_market_currency = risk_wallet / usdt_to_irt_rate
                    elif ("تومان" in market_type or "طلا" in market_type) and wallet_currency in ["تتر (USDT)", "دلار ($)"]:
                        risk_in_market_currency = risk_wallet * usdt_to_irt_rate
                    else:
                        risk_in_market_currency = risk_wallet

                    pos_size = risk_in_market_currency / price_distance
                    pos_value = pos_size * float(entry_p)
                    pos_value_unit = "تومان" if ("تومان" in market_type or "طلا" in market_type) else "تتر/دلار"

            # فیلدهای جدید: لینک تصویر موقعیت و یادداشت‌های معامله
            st.markdown("---")
            col_img_pos, col_notes = st.columns(2)
            with col_img_pos:
                position_image_url = st.text_input(
                    "🔗 لینک تصویر ورود / پوزیشن:",
                    value=str(loaded_data.get("Link Tasvir Position", "")),
                    placeholder="لینک چارت در زمان ورود یا اسکرین‌شات متاتریدر...",
                    key=f"img_pos_{trade_id_val}"
                )
            with col_notes:
                trade_notes = st.text_area(
                    "📝 یادداشت‌ها و نکات ستاپ:",
                    value=str(loaded_data.get("Yaddasht-ha", "")),
                    placeholder="هر نکته‌ای در مورد مدیریت پوزیشن، احساسات، دلیل ورود یا سناریوی مدیریت...",
                    key=f"notes_{trade_id_val}"
                )

            # نمایش آنی نتایج و متریک‌ها
            st.markdown("---")
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("حجم سفارش جهت ورود", f"{pos_size:,.4f} {target_vol_unit}")
            col_m2.metric("ارزش کل موقعیت", f"{pos_value:,.2f} {pos_value_unit}")
            col_m3.metric("سرمایه در ریسک", f"{risk_wallet:,.2f} {wallet_currency} ({actual_risk_pct}%)")

            # دکمه ثبت پوزیشن
            submit_trade = st.button("🚀 ثبت قطعی و ورود به معامله (Open Trade)", use_container_width=True, key=f"btn_open_{trade_id_val}")

            if submit_trade:
                if not symbol:
                    st.error("❌ ابتدا نماد معامله را در بالای صفحه مشخص کنید.")
                else:
                    details["Balance"] = f"{balance} {wallet_currency}"
                    details["Emtiyaze 3 Marhale"] = total_score_3m
                    details["Grade"] = grade
                    details["Darsade Risk"] = f"{actual_risk_pct}%"
                    details["Risk ($)"] = f"{round(risk_wallet, 2)} {wallet_currency}"
                    details["Hajm (Lot)"] = f"{round(pos_size, 4)} {target_vol_unit}"
                    details["Vaziyat"] = "Baz (Open)"
                    details["Noe TP / Khorooj"] = "Dar Intizar Khorooj"
                    details["Natijeh (PnL $)"] = ""
                    details["R:R Vaghei"] = ""
                    details["Link Tasvir Position"] = position_image_url
                    details["Yaddasht-ha"] = trade_notes

                    if upsert_trade(details):
                        st.session_state["current_trade_id"] = generate_trade_id()
                        st.session_state["reset_to_new"] = True
                        st.success(f"پوزیشن {trade_id_val} با موفقیت ثبت شد.")
                        st.rerun()

# =========================================================
# TAB 2: UPDATE CLOSED TRADE
# =========================================================
with tab2:
    st.markdown("### 📝 ثبت خروج و بستن موقعیت‌های معاملاتی")
    df = load_data()

    if df.empty or "Vaziyat" not in df.columns:
        st.info("داده‌ای یافت نشد.")
    else:
        open_trades = df[df["Vaziyat"] == "Baz (Open)"]
        if open_trades.empty:
            st.success("✅ در حال حاضر هیچ پوزیشن بازی وجود ندارد.")
        else:
            with st.container(border=True):
                trade_lookup = {
                    f"شناسه: {row.get('Trade ID', '')} | نماد: {row.get('Namad', '')} | جهت: {row.get('Jahat (Buy/Sell)', '')} | تاریخ: {row.get('Tarikh', '')}": row.get("Trade ID")
                    for _, row in open_trades.iterrows()
                }
                selected_label = st.selectbox("انتخاب پوزیشن باز:", options=list(trade_lookup.keys()))
                target_trade_id = trade_lookup[selected_label]
                selected_trade_data = open_trades[open_trades["Trade ID"] == target_trade_id].iloc[0].to_dict()

            with st.container(border=True):
                status_opts = {"1": ("بسته‌شده با نتیجه مشخص (Closed Trade)", "CLOSED"), "2": ("لغوشده / نرسیده به نقطه ورود (Canceled)", "CANCELED")}
                status_sel = st.radio("وضعیت خروج معامله:", list(status_opts.keys()), format_func=lambda x: status_opts[x][0])
                status_code = status_opts[status_sel][1]

                if status_code == "CANCELED":
                    if st.button("ثبت لغو معامله", use_container_width=True):
                        selected_trade_data["Vaziyat"] = "Laghv-shode (Canceled/Missed)"
                        selected_trade_data["Noe TP / Khorooj"] = "Nareside be Entry"
                        selected_trade_data["Natijeh (PnL $)"] = "0.0"
                        selected_trade_data["R:R Vaghei"] = "0.0"
                        if upsert_trade(selected_trade_data):
                            st.warning(f"پوزیشن {target_trade_id} لغو شد.")
                            st.rerun()
                else:
                    with st.form("close_trade_form"):
                        exit_opts = {
                            "1": ("🎯 حد سود اول / خروج اسکالپ (۵۰٪ نقد + ریسک‌فری)", "TP1_SCALP"),
                            "2": ("🎯 حد سود دوم / تارگت اصلی (زون مقابل MTF)", "TP2_MAIN"),
                            "3": ("🎯 حد سود سوم / تارگت رانر (سقف/کف تایم بالا)", "TP3_RUNNER"),
                            "4": ("🛑 برخورد به حد ضرر (Stop Loss)", "SL_HIT"),
                            "5": ("⚖️ خروج سر‌به‌سر / ریسک‌فری (Break Even)", "BREAK_EVEN"),
                        }
                        exit_sel = st.selectbox("دلیل و نحوه خروج:", list(exit_opts.keys()), format_func=lambda x: exit_opts[x][0])

                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            pnl_val = st.number_input("سود / زیان دلاری (PnL $):", value=0.0, step=10.0)
                        with col_c2:
                            rr_val = st.number_input("نسبت ریسک به ریوارد واقعی (R:R):", value=0.0, step=0.1)

                        save_close = st.form_submit_button("💾 ثبت نهایی خروج معامله", use_container_width=True)
                        if save_close:
                            selected_trade_data["Vaziyat"] = "Baste-shode (Closed)"
                            selected_trade_data["Noe TP / Khorooj"] = exit_opts[exit_sel][0]
                            selected_trade_data["Natijeh (PnL $)"] = str(pnl_val)
                            selected_trade_data["R:R Vaghei"] = str(rr_val)
                            if upsert_trade(selected_trade_data):
                                st.success(f"معامله {target_trade_id} با موفقیت بسته شد.")
                                st.rerun()

# =========================================================
# TAB 3: ADVANCED ANALYTICS DASHBOARD
# =========================================================
with tab3:
    st.markdown("### 📊 داشبورد تحلیل عملکرد و مدیریت حساب")
    df = load_data()

    if df.empty or "Vaziyat" not in df.columns:
        st.info("هنوز دیتایی برای تحلیل ثبت نشده است.")
    else:
        df_calc = df.copy()
        df_calc["Natijeh (PnL $)"] = pd.to_numeric(df_calc["Natijeh (PnL $)"], errors="coerce").fillna(0.0)
        df_calc["R:R Vaghei"] = pd.to_numeric(df_calc["R:R Vaghei"], errors="coerce").fillna(0.0)

        closed_trades = df_calc[df_calc["Vaziyat"] == "Baste-shode (Closed)"].copy()
        canceled_count = len(df_calc[df_calc["Vaziyat"] == "Laghv-shode (Canceled/Missed)"])

        if closed_trades.empty:
            st.info("هیچ معامله بسته‌شده‌ای برای استخراج آمار وجود ندارد.")
            st.metric("معاملات لغوشده", canceled_count)
        else:
            total_closed = len(closed_trades)
            wins = len(closed_trades[closed_trades["Natijeh (PnL $)"] > 0])
            losses = len(closed_trades[closed_trades["Natijeh (PnL $)"] < 0])
            breakevens = len(closed_trades[closed_trades["Natijeh (PnL $)"] == 0])

            win_rate = (wins / total_closed) * 100 if total_closed > 0 else 0.0
            total_pnl = closed_trades["Natijeh (PnL $)"].sum()
            avg_rr = closed_trades["R:R Vaghei"].mean()

            gross_profit = closed_trades[closed_trades["Natijeh (PnL $)"] > 0]["Natijeh (PnL $)"].sum()
            gross_loss = abs(closed_trades[closed_trades["Natijeh (PnL $)"] < 0]["Natijeh (PnL $)"].sum())
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

            closed_trades["Equity"] = closed_trades["Natijeh (PnL $)"].cumsum()
            closed_trades["Peak"] = closed_trades["Equity"].cummax()
            closed_trades["Drawdown"] = closed_trades["Peak"] - closed_trades["Equity"]
            max_dd = closed_trades["Drawdown"].max() if not closed_trades.empty else 0.0

            kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
            kpi1.metric("کل سود/زیان", f"${total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")
            kpi2.metric("وین‌ریت (Win Rate)", f"{win_rate:.1f}%")
            kpi3.metric("پرافیت فاکتور (PF)", f"{profit_factor:.2f}")
            kpi4.metric("میانگین R:R", f"{avg_rr:.2f}")
            kpi5.metric("حداکثر افت سرمایه (DD)", f"${max_dd:,.2f}", delta_color="inverse")

            st.write("")

            ch_col1, ch_col2 = st.columns([1, 1.8])
            with ch_col1:
                with st.container(border=True):
                    fig_gauge = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=win_rate,
                        number={'suffix': "%", 'font': {'color': '#f0f6fc', 'size': 32}},
                        gauge={
                            'axis': {'range': [0, 100], 'tickcolor': "#8b949e"},
                            'bar': {'color': "#10b981" if win_rate >= 50 else "#f87171"},
                            'bgcolor': "#161b22",
                            'steps': [
                                {'range': [0, 40], 'color': "rgba(239, 68, 68, 0.2)"},
                                {'range': [40, 60], 'color': "rgba(234, 179, 8, 0.2)"},
                                {'range': [60, 100], 'color': "rgba(16, 185, 129, 0.2)"}
                            ],
                        }
                    ))
                    fig_gauge.update_layout(
                        title={'text': "نرخ برد استراتژی", 'y': 0.9, 'x': 0.5, 'xanchor': 'center', 'font': {'color': '#f0f6fc'}},
                        paper_bgcolor="#0e1117",
                        plot_bgcolor="#0e1117",
                        height=280,
                        margin=dict(l=30, r=30, t=50, b=20),
                    )
                    st.plotly_chart(fig_gauge, use_container_width=True)

            with ch_col2:
                with st.container(border=True):
                    closed_trades["Trade_Number"] = range(1, len(closed_trades) + 1)
                    fig_eq = go.Figure()
                    fig_eq.add_trace(go.Scatter(
                        x=closed_trades["Trade_Number"],
                        y=closed_trades["Equity"],
                        mode='lines+markers',
                        name='Equity Curve',
                        line=dict(color='#3b82f6', width=3),
                        marker=dict(size=6, color='#60a5fa'),
                        fill='tozeroy',
                        fillcolor='rgba(59, 130, 246, 0.1)'
                    ))
                    fig_eq.update_layout(
                        title={'text': "رشد تجمعی سود (Equity Curve)", 'font': {'color': '#f0f6fc'}},
                        paper_bgcolor="#0e1117",
                        plot_bgcolor="#0e1117",
                        font={'color': '#8b949e'},
                        xaxis=dict(title="شماره معامله", gridcolor='#21262d', showgrid=True),
                        yaxis=dict(title="سود تجمعی ($)", gridcolor='#21262d', showgrid=True),
                        height=280,
                        margin=dict(l=40, r=20, t=50, b=40),
                    )
                    st.plotly_chart(fig_eq, use_container_width=True)

            with st.container(border=True):
                bar_colors = ['#10b981' if p >= 0 else '#ef4444' for p in closed_trades["Natijeh (PnL $)"]]
                fig_bar = go.Figure(go.Bar(
                    x=closed_trades["Trade ID"],
                    y=closed_trades["Natijeh (PnL $)"],
                    marker_color=bar_colors,
                    hovertemplate="معامله: %{x}<br>سود/زیان: $%{y:.2f}<extra></extra>"
                ))
                fig_bar.update_layout(
                    title={'text': "سود و زیان به تفکیک هر موقعیت", 'font': {'color': '#f0f6fc'}},
                    paper_bgcolor="#0e1117",
                    plot_bgcolor="#0e1117",
                    font={'color': '#8b949e'},
                    xaxis=dict(title="شناسه معامله", gridcolor='#21262d', tickangle=-45),
                    yaxis=dict(title="سود/زیان ($)", gridcolor='#21262d'),
                    height=300,
                    margin=dict(l=40, r=20, t=50, b=60),
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            with st.container(border=True):
                st.markdown("##### 📑 تاریخچه کامل داده‌ها")
                st.dataframe(df, use_container_width=True)
