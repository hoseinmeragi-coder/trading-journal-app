import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection

# --- تنظیمات صفحه ---
st.set_page_config(
    page_title="سیستم ژورنال معاملاتی (نسخه ابری)",
    page_icon="🎯",
    layout="wide",
)

# اتصال به دیتابیس ابری گوگل‌شیت
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read(worksheet="Sheet1", ttl="0m")
        if df is None or df.empty:
            return pd.DataFrame()
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()

def save_data(df):
    try:
        conn.update(worksheet="Sheet1", data=df)
    except Exception:
        # اگر برگه هنوز ساخته نشده باشد، آن را ایجاد و ذخیره می‌کند
        conn.create(worksheet="Sheet1", data=df)

def generate_trade_id():
    now = datetime.datetime.now()
    return f"TRD-{now.strftime('%Y%m%d-%H%M%S')}"

if "current_trade_id" not in st.session_state:
    st.session_state["current_trade_id"] = generate_trade_id()

# CSS سفارشی
st.markdown(
    """
    <style>
    .stSelectbox label, .stTextInput label, .stNumberInput label, .stTimeInput label {
        font-weight: bold;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #e9ecef;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

tab1, tab2, tab3 = st.tabs(
    [
        "🎯 آنالیز و ثبت معامله جدید",
        "📝 ثبت خروج و مدیریت پوزیشن",
        "📊 آمار و تحلیل عملکرد",
    ]
)

# =========================================================
# TAB 1: ADD / EDIT ANALYSIS & TRADE
# =========================================================
with tab1:
    st.title("🎯 آنالیز و ثبت معامله جدید (نسخه ۴ - استاندارد ۱۰۰ امتیازی)")
    st.caption("سیستم هوشمند ارزیابی و آنالیز زون‌های معاملاتی (ذخیره‌سازی ابری)")

    loaded_data = {}
    df_all = load_data()

    if not df_all.empty and "Vaziyat" in df_all.columns:
        draft_trades = df_all[df_all["Vaziyat"] == "Pishnevis (Draft)"]

        if not draft_trades.empty:
            st.info("📌 تحلیل‌های نیمه‌کاره قبلی (پیش‌نویس) یافت شد.")
            draft_dict = {
                f"[{idx}] شناسه: {row['Trade ID']} | نماد: {row['Namad']} | جهت: {row.get('Jahat (Buy/Sell)', '')} | ساعت: {row.get('Saate Candle/Zone', '')}": idx
                for idx, row in draft_trades.iterrows()
            }
            draft_options = ["-- ایجاد تحلیل جدید --"] + list(draft_dict.keys())

            col_sel_draft, col_del_draft = st.columns([4, 1])
            with col_sel_draft:
                selected_draft = st.selectbox("📂 انتخاب تحلیل نیمه‌کاره جهت ادامه و ویرایش:", draft_options)

            with col_del_draft:
                st.write("")
                st.write("")
                if selected_draft != "-- ایجاد تحلیل جدید --":
                    if st.button("🗑️ حذف این تحلیل", use_container_width=True):
                        del_idx = draft_dict[selected_draft]
                        target_del_id = df_all.loc[del_idx, "Trade ID"]
                        df_all = df_all[df_all["Trade ID"] != target_del_id]
                        save_data(df_all)
                        if st.session_state.get("current_trade_id") == target_del_id:
                            st.session_state["current_trade_id"] = generate_trade_id()
                        st.warning(f"تحلیل با شناسه {target_del_id} حذف شد.")
                        st.rerun()

            if selected_draft != "-- ایجاد تحلیل جدید --":
                draft_idx = draft_dict[selected_draft]
                loaded_data = df_all.loc[draft_idx].to_dict()
                st.session_state["current_trade_id"] = loaded_data.get("Trade ID", st.session_state["current_trade_id"])
            else:
                if st.session_state["current_trade_id"] == loaded_data.get("Trade ID"):
                    st.session_state["current_trade_id"] = generate_trade_id()

    col_id, col_sym, col_dir = st.columns(3)
    with col_id:
        trade_id_val = st.session_state["current_trade_id"]
        st.text_input("شناسه معامله (Trade ID):", value=trade_id_val, disabled=True)
    with col_sym:
        default_sym = loaded_data.get("Namad", "") if pd.notna(loaded_data.get("Namad")) else ""
        symbol = st.text_input("نام نماد معاملاتی (مثلاً EURUSD, XAUUSD):", value=default_sym).strip().upper()
    with col_dir:
        direction_options = ["خرید (Buy / Demand)", "فروش (Sell / Supply)"]
        default_dir_idx = 0
        if loaded_data.get("Jahat (Buy/Sell)") in direction_options:
            default_dir_idx = direction_options.index(loaded_data.get("Jahat (Buy/Sell)"))
        trade_direction = st.selectbox("دیدگاه معامله روی ناحیه:", direction_options, index=default_dir_idx)

    st.markdown("---")
    st.subheader("📌 مرحله ۱: چند سناریوی اصلی بیس / زون (حداکثر ۳۰ امتیاز)")

    scenario_options = {
        "0": ("-- انتخاب نشده --", "NONE"),
        "1": ("بیس سریع (RBR / DBD / RBD / DBR)", "DIRECT_BASE"),
        "2": ("فلیپ زون یا بیس پنهان در گذشته (Historical)", "FLIP_ZONE"),
        "3": ("کندل منشأ شکست (BOS / CHoCH / OrderBlock)", "CANDLE_OB"),
    }

    zone_tf_options = {
        "0": "-- انتخاب نشده --", "1": "ماهانه (Monthly / 1M)", "2": "هفتگی (Weekly / 1W)",
        "3": "سه روزه (3D)", "4": "روزانه (Daily / 1D)", "5": "۱۲ ساعته (12H)",
        "6": "۸ ساعته (8H)", "7": "۶ ساعته (6H)", "8": "۴ ساعته (4H)",
        "9": "۳ ساعته (3H)", "10": "۲ ساعته (2H)", "11": "۱ ساعته (1H)",
        "12": "۴۵ دقیقه (45M)", "13": "۳۰ دقیقه (30M)", "14": "۲۰ دقیقه (20M)",
        "15": "۱۵ دقیقه (15M)", "16": "۱۰ دقیقه (10M)", "17": "۵ دقیقه (5M)",
        "18": "۳ دقیقه (3M)", "19": "۲ دقیقه (2M)"
    }

    def get_index_by_val(d, target_val, default=0):
        if not target_val or pd.isna(target_val) or target_val == "-- انتخاب نشده --":
            return default
        for idx, (k, v) in enumerate(d.items()):
            val_text = v[0] if isinstance(v, tuple) else v
            if str(val_text).strip() == str(target_val).strip():
                return idx
        return default

    col_scen, col_ztf, col_date, col_time = st.columns(4)
    with col_scen:
        scen_default_idx = get_index_by_val(scenario_options, loaded_data.get("Senarioye Asli Zone"))
        selected_scenario_key = st.selectbox(
            "مبدأ اصلی Zone شما از چه نوعی است؟",
            options=list(scenario_options.keys()),
            index=scen_default_idx,
            format_func=lambda x: f"[{x}] {scenario_options[x][0]}" if x != "0" else scenario_options[x][0],
        )
    with col_ztf:
        ztf_default_idx = get_index_by_val(zone_tf_options, loaded_data.get("Timeframe Candle/Zone"))
        selected_zone_tf_key = st.selectbox(
            "تایم‌فریم کندل / ناحیه:",
            options=list(zone_tf_options.keys()),
            index=ztf_default_idx,
            format_func=lambda x: zone_tf_options[x],
        )
    with col_date:
        default_date_str = loaded_data.get("Tarikh Candle/Zone", "")
        candle_date_str = st.text_input(
            "تاریخ کندل / ناحیه (مثلاً 2026-08-25):",
            value="" if pd.isna(default_date_str) else str(default_date_str),
            placeholder="مثلاً 2026-08-25",
        ).strip()
    with col_time:
        default_time_str = loaded_data.get("Saate Candle/Zone", "")
        candle_time_str = st.text_input(
            "ساعت کندل / ناحیه (مثلاً 14:23):",
            value="" if pd.isna(default_time_str) else str(default_time_str),
            placeholder="مثلاً 14:23",
        ).strip()

    scenario_info = scenario_options[selected_scenario_key]
    scenario_code = scenario_info[1]
    zone_timeframe_val = zone_tf_options[selected_zone_tf_key]

    score_m1 = 0
    details = {
        "Trade ID": trade_id_val,
        "Tarikh": loaded_data.get("Tarikh", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
        "Namad": symbol,
        "Jahat (Buy/Sell)": trade_direction,
        "Senarioye Asli Zone": scenario_info[0],
        "Timeframe Candle/Zone": zone_timeframe_val,
        "Tarikh Candle/Zone": candle_date_str,
        "Saate Candle/Zone": candle_time_str,
    }

    if scenario_code != "NONE":
        st.markdown("#### سوالات اختصاصی سناریوی انتخاب‌شده:")
        col_s1, col_s2 = st.columns(2)

        if scenario_code == "DIRECT_BASE":
            with col_s1:
                patt_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("RBR یا DBD (ادامه‌دهنده)", 4), "2": ("RBD یا DBR (بازگشتی)", 4)}
                patt_sel = st.selectbox("۱.۱. نوع الگوی بیس؟", list(patt_opts.keys()), index=get_index_by_val(patt_opts, loaded_data.get("1.1 Olgooye Base")), format_func=lambda x: patt_opts[x][0])
                score_m1 += patt_opts[patt_sel][1]
                details["1.1 Olgooye Base"] = patt_opts[patt_sel][0]

                fresh_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("کاملاً تازه و تست‌نشده (Fresh)", 5), "2": ("یک‌بار تست‌شده همراه با واکنش", 2), "3": ("تست‌شده و کهنه", 0)}
                fresh_sel = st.selectbox("۱.۲. وضعیت دست‌نخوردگی (Freshness)؟", list(fresh_opts.keys()), index=get_index_by_val(fresh_opts, loaded_data.get("1.2 Freshness Base")), format_func=lambda x: fresh_opts[x][0])
                score_m1 += fresh_opts[fresh_sel][1]
                details["1.2 Freshness Base"] = fresh_opts[fresh_sel][0]

                count_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("۱ تا ۳ کندل (قوی)", 4), "2": ("۳ تا ۵ کندل (متوسط)", 2), "3": ("بیشتر از ۵ کندل (ضعیف)", 0)}
                count_sel = st.selectbox("۱.۳. تعداد کندل‌های داخل بیس؟", list(count_opts.keys()), index=get_index_by_val(count_opts, loaded_data.get("1.3 Tedad Candle Base")), format_func=lambda x: count_opts[x][0])
                score_m1 += count_opts[count_sel][1]
                details["1.3 Tedad Candle Base"] = count_opts[count_sel][0]

                type_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("دوجی / فشرده و منشأ بیس (Origin)", 4), "2": ("ماروبوزو یا بیس میانی", 2)}
                type_sel = st.selectbox("۱.۴. شکل کندل‌های بیس و جایگاه آن؟", list(type_opts.keys()), index=get_index_by_val(type_opts, loaded_data.get("1.4 Shekl va Jaygahe Base")), format_func=lambda x: type_opts[x][0])
                score_m1 += type_opts[type_sel][1]
                details["1.4 Shekl va Jaygahe Base"] = type_opts[type_sel][0]

            with col_s2:
                dep_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بدنه بلند و کلوز نزدیک + FVG + ۲ کندل ادامه‌دار", 5), "2": ("بدنه متوسط یا FVG ضعیف", 2), "3": ("خروج ضعیف و کم‌رمق", 0)}
                dep_sel = st.selectbox("۱.۵. خروج از بیس (Departure Body & FVG)؟", list(dep_opts.keys()), index=get_index_by_val(dep_opts, loaded_data.get("1.5 Khorooje Base (Departure)")), format_func=lambda x: dep_opts[x][0])
                score_m1 += dep_opts[dep_sel][1]
                details["1.5 Khorooje Base (Departure)"] = dep_opts[dep_sel][0]

                pip_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("حرکت قوی و ادامه‌دار (پرتاب لگ استاندارد)", 3), "2": ("حرکت کم و سریعاً وارد اصلاح شد", 1)}
                pip_sel = st.selectbox("۱.۶. میزان پرتاب لگ؟", list(pip_opts.keys()), index=get_index_by_val(pip_opts, loaded_data.get("1.6 Mizane Parthabe Lag")), format_func=lambda x: pip_opts[x][0])
                score_m1 += pip_opts[pip_sel][1]
                details["1.6 Mizane Parthabe Lag"] = pip_opts[pip_sel][0]

                ach_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("BOS قوی یا حذف زون مقابل (Removal)", 5), "2": ("BOS خرد یا هانت/سوئیپ", 2), "3": ("بدون دستاورد", 0)}
                ach_sel = st.selectbox("۱.۷. دستاورد بیس (Achievement)؟", list(ach_opts.keys()), index=get_index_by_val(ach_opts, loaded_data.get("1.7 Dastavard Base")), format_func=lambda x: ach_opts[x][0])
                score_m1 += ach_opts[ach_sel][1]
                details["1.7 Dastavard Base"] = ach_opts[ach_sel][0]

        elif scenario_code == "FLIP_ZONE":
            with col_s1:
                ftype_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("فلیپ زون (سطح تبدیل‌شده)", 5), "2": ("بیس پنهان در گذشته", 3)}
                ftype_sel = st.selectbox("۱.۱. جنس ناحیه؟", list(ftype_opts.keys()), index=get_index_by_val(ftype_opts, loaded_data.get("1.1 Jense Nahiye")), format_func=lambda x: ftype_opts[x][0])
                score_m1 += ftype_opts[ftype_sel][1]
                details["1.1 Jense Nahiye"] = ftype_opts[ftype_sel][0]

                fresh_flip_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("کاملاً تازه و تست‌نشده (Fresh)", 5), "2": ("یک‌بار تست‌شده همراه با واکنش", 2), "3": ("تست‌شده و کهنه", 0)}
                fresh_flip_sel = st.selectbox("۱.۲. تازگی فلیپ (Freshness)؟", list(fresh_flip_opts.keys()), index=get_index_by_val(fresh_flip_opts, loaded_data.get("1.2 Freshness Flip")), format_func=lambda x: fresh_flip_opts[x][0])
                score_m1 += fresh_flip_opts[fresh_flip_sel][1]
                details["1.2 Freshness Flip"] = fresh_flip_opts[fresh_flip_sel][0]

                fbreak_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("شکست شارپ با ماروبوزو و بدنه بلند", 5), "2": ("شکست ضعیف یا با سایه (Shadow)", 2)}
                fbreak_sel = st.selectbox("۱.۳. کیفیت شکستی که فلیپ را ساخته؟", list(fbreak_opts.keys()), index=get_index_by_val(fbreak_opts, loaded_data.get("1.3 Keifiyaat Shekaste Flip")), format_func=lambda x: fbreak_opts[x][0])
                score_m1 += fbreak_opts[fbreak_sel][1]
                details["1.3 Keifiyaat Shekaste Flip"] = fbreak_opts[fbreak_sel][0]

            with col_s2:
                frem_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بله، زون مقابل را کاملاً پاک کرده", 5), "2": ("خیر، واکنش ضعیف بوده", 1)}
                frem_sel = st.selectbox("۱.۴. حذف زون مقابل (Removal)؟", list(frem_opts.keys()), index=get_index_by_val(frem_opts, loaded_data.get("1.4 Removal Zone Moghabel")), format_func=lambda x: frem_opts[x][0])
                score_m1 += frem_opts[frem_sel][1]
                details["1.4 Removal Zone Moghabel"] = frem_opts[frem_sel][0]

                fsweep_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بله، قبل از شکست سوئیپ داشته", 5), "2": ("خیر", 1)}
                fsweep_sel = st.selectbox("۱.۵. سوئیپ نقدینگی در گذشته این سطح؟", list(fsweep_opts.keys()), index=get_index_by_val(fsweep_opts, loaded_data.get("1.5 Sweep Naghdinegi Sath")), format_func=lambda x: fsweep_opts[x][0])
                score_m1 += fsweep_opts[fsweep_sel][1]
                details["1.5 Sweep Naghdinegi Sath"] = fsweep_opts[fsweep_sel][0]

                ffvg_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("FVG واضح و پرنشده وجود دارد", 5), "2": ("FVG وجود ندارد یا پر شده", 1)}
                ffvg_sel = st.selectbox("۱.۶. وضعیت FVG در محدوده فلیپ؟", list(ffvg_opts.keys()), index=get_index_by_val(ffvg_opts, loaded_data.get("1.6 Vaziyaate FVG Flip")), format_func=lambda x: ffvg_opts[x][0])
                score_m1 += ffvg_opts[ffvg_sel][1]
                details["1.6 Vaziyaate FVG Flip"] = ffvg_opts[ffvg_sel][0]

        elif scenario_code == "CANDLE_OB":
            with col_s1:
                cbreak_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("BOS ماژور یا CHoCH اصلی", 5), "2": ("BOS اینترنال (خرد)", 2)}
                cbreak_sel = st.selectbox("۱.۱. نوع شکستی که این کندل ساخته؟", list(cbreak_opts.keys()), index=get_index_by_val(cbreak_opts, loaded_data.get("1.1 Noe Shekaste Candle")), format_func=lambda x: cbreak_opts[x][0])
                score_m1 += cbreak_opts[cbreak_sel][1]
                details["1.1 Noe Shekaste Candle"] = cbreak_opts[cbreak_sel][0]

                fresh_cand_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("کاملاً تازه و تست‌نشده (Fresh)", 5), "2": ("یک‌بار تست‌شده همراه با واکنش", 2), "3": ("تست‌شده و کهنه", 0)}
                fresh_cand_sel = st.selectbox("۱.۲. تازگی کندل منشأ (Freshness)؟", list(fresh_cand_opts.keys()), index=get_index_by_val(fresh_cand_opts, loaded_data.get("1.2 Freshness Candle")), format_func=lambda x: fresh_cand_opts[x][0])
                score_m1 += fresh_cand_opts[fresh_cand_sel][1]
                details["1.2 Freshness Candle"] = fresh_cand_opts[fresh_cand_sel][0]

                csweep_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بله، هانت / سوئیپ اکستریم داشته", 5), "2": ("خیر، سوئیپ نداشته", 1)}
                csweep_sel = st.selectbox("۱.۳. سوئیپ قبل از حرکت؟", list(csweep_opts.keys()), index=get_index_by_val(csweep_opts, loaded_data.get("1.3 Sweep Ghabl Shillik")), format_func=lambda x: csweep_opts[x][0])
                score_m1 += csweep_opts[csweep_sel][1]
                details["1.3 Sweep Ghabl Shillik"] = csweep_opts[csweep_sel][0]

            with col_s2:
                cfvg_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("FVG واضح و قوی بلافاصله بعد از کندل", 5), "2": ("بدون FVG", 1)}
                cfvg_sel = st.selectbox("۱.۴. وضعیت FVG بعد از کندل؟", list(cfvg_opts.keys()), index=get_index_by_val(cfvg_opts, loaded_data.get("1.4 FVG Ba'ad Candle")), format_func=lambda x: cfvg_opts[x][0])
                score_m1 += cfvg_opts[cfvg_sel][1]
                details["1.4 FVG Ba'ad Candle"] = cfvg_opts[cfvg_sel][0]

                cbody_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بدنه کشیده و کلوز نزدیک به سقف/کف", 5), "2": ("کندل با سایه بلند و بدنه کوچک", 2)}
                cbody_sel = st.selectbox("۱.۵. کیفیت بدنه و کلوز کندل؟", list(cbody_opts.keys()), index=get_index_by_val(cbody_opts, loaded_data.get("1.5 Keifiyaat Body Candle")), format_func=lambda x: cbody_opts[x][0])
                score_m1 += cbody_opts[cbody_sel][1]
                details["1.5 Keifiyaat Body Candle"] = cbody_opts[cbody_sel][0]

                cfollow_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("حداقل ۲ کندل قوی و هم‌جهت بعد از آن", 5), "2": ("سریعاً وارد اصلاح شد", 1)}
                cfollow_sel = st.selectbox("۱.۶. تداوم حرکت (Follow-through)؟", list(cfollow_opts.keys()), index=get_index_by_val(cfollow_opts, loaded_data.get("1.6 Tadaome Harakat Ba'ad Candle")), format_func=lambda x: cfollow_opts[x][0])
                score_m1 += cfollow_opts[cfollow_sel][1]
                details["1.6 Tadaome Harakat Ba'ad Candle"] = cfollow_opts[cfollow_sel][0]

    # =========================================================
    # MARHALE 2: TIMEFRAME & HTF CONTEXT
    # =========================================================
    st.markdown("---")
    st.subheader("📌 مرحله ۲: قفل تایم‌فریم و کانتکست تایم بالا HTF (حداکثر ۴۰ امتیاز)")

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

        tf_sel = st.selectbox("تایم‌فریم اصلی زون (MTF) را انتخاب کنید:", list(tf_options.keys()), index=tf_default_idx, format_func=lambda x: tf_options[x][0])
        mtf = tf_options[tf_sel][1]
        details["Timeframe Zone (MTF)"] = mtf

        score_m2 = 0
        htf_bias_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بله، کاملاً هم‌جهت با روند تایم بالا (HTF)", 12), "2": ("خیر، معامله اصلاحی / خلاف روند تایم بالا", 0)}
        htf_bias_sel = st.selectbox("۲.۱. هم‌جهتی با تایم بالا (HTF)؟", list(htf_bias_opts.keys()), index=get_index_by_val(htf_bias_opts, loaded_data.get("2.1 Ham-jehati ba HTF")), format_func=lambda x: htf_bias_opts[x][0])
        score_m2 += htf_bias_opts[htf_bias_sel][1]
        details["2.1 Ham-jehati ba HTF"] = htf_bias_opts[htf_bias_sel][0]

        htf_curve_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("کاملاً مناسب و فاصله کافی (حداقل R:R ۱ به ۲)", 10), "2": ("نزدیک به زون مقابل تایم بالا (پرریسک)", 0)}
        htf_curve_sel = st.selectbox("۲.۲. موقعیت زون روی منحنی و فاصله تا مانع HTF؟", list(htf_curve_opts.keys()), index=get_index_by_val(htf_curve_opts, loaded_data.get("2.2 Mogheiyat rooye Curve")), format_func=lambda x: htf_curve_opts[x][0])
        score_m2 += htf_curve_opts[htf_curve_sel][1]
        details["2.2 Mogheiyat rooye Curve"] = htf_curve_opts[htf_curve_sel][0]

    with col_m2_2:
        htf_power_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("لگ‌های موافق قوی و اصلاح‌ها کوتاه/ضعیف", 10), "2": ("اصلاح‌ها عمیق و حرکت در حال ضعیف شدن", 3)}
        htf_power_sel = st.selectbox("۲.۳. موازنه قدرت و مقایسه لگ‌ها و کندل‌ها؟", list(htf_power_opts.keys()), index=get_index_by_val(htf_power_opts, loaded_data.get("2.3 Movazene Ghodrat Lag-ha")), format_func=lambda x: htf_power_opts[x][0])
        score_m2 += htf_power_opts[htf_power_sel][1]
        details["2.3 Movazene Ghodrat Lag-ha"] = htf_power_opts[htf_power_sel][0]

        htf_struct_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("رونددار و با گام‌های حرکتی قوی (Trending)", 8), "2": ("در محدوده فشرده و رنج (Ranging)", 2)}
        htf_struct_sel = st.selectbox("۲.۴. وضعیت حرکت تایم بالا (Trend/Range)؟", list(htf_struct_opts.keys()), index=get_index_by_val(htf_struct_opts, loaded_data.get("2.4 Vaziyaat HTF (Trend/Range)")), format_func=lambda x: htf_struct_opts[x][0])
        score_m2 += htf_struct_opts[htf_struct_sel][1]
        details["2.4 Vaziyaat HTF (Trend/Range)"] = htf_struct_opts[htf_struct_sel][0]

    # =========================================================
    # MARHALE 3: APPROACH & PRE-ENTRY LIQUIDITY
    # =========================================================
    st.markdown("---")
    st.subheader("📌 مرحله ۳: نحوه رسیدن قیمت به ناحیه (حداکثر ۳۰ امتیاز)")

    col_m3_1, col_m3_2 = st.columns(2)
    score_m3 = 0

    with col_m3_1:
        app_type_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("فشرده / اصلاحی (Compression)", 12), "2": ("حرکت معمولی", 6), "3": ("اسپایک / شارپ و پرفشار", 0)}
        app_type_sel = st.selectbox("۳.۱. نحوه رسیدن قیمت به زون؟", list(app_type_opts.keys()), index=get_index_by_val(app_type_opts, loaded_data.get("3.1 Nahveye Rasidan (Approach)")), format_func=lambda x: app_type_opts[x][0])
        score_m3 += app_type_opts[app_type_sel][1]
        details["3.1 Nahveye Rasidan (Approach)"] = app_type_opts[app_type_sel][0]

        app_liq_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("ایندیوسمنت ساخته شده یا قبل از زون سوئیپ انجام شده", 10), "2": ("بدون سوئیپ و ایندیوسمنت", 2)}
        app_liq_sel = st.selectbox("۳.۲. نقدینگی قبل از رسیدن (Inducement/Sweep)؟", list(app_liq_opts.keys()), index=get_index_by_val(app_liq_opts, loaded_data.get("3.2 Naghdinegi Ghabl Zone")), format_func=lambda x: app_liq_opts[x][0])
        score_m3 += app_liq_opts[app_liq_sel][1]
        details["3.2 Naghdinegi Ghabl Zone"] = app_liq_opts[app_liq_sel][0]

    with col_m3_2:
        app_mom_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("کندل‌ها در حال تضعیف و کاهش اندازه بدنه", 8), "2": ("ورود با کندل‌های پرقدرت و بدنه بلند", 1)}
        app_mom_sel = st.selectbox("۳.۳. مومنتوم و بدنه کندل‌ها نزدیک به زون؟", list(app_mom_opts.keys()), index=get_index_by_val(app_mom_opts, loaded_data.get("3.3 Momentum Nazdik Zone")), format_func=lambda x: app_mom_opts[x][0])
        score_m3 += app_mom_opts[app_mom_sel][1]
        details["3.3 Momentum Nazdik Zone"] = app_mom_opts[app_mom_sel][0]

    total_score_3m = score_m1 + score_m2 + score_m3
    st.markdown("---")
    st.info(f"📊 مجموع امتیاز ۳ مرحله اول: **{total_score_3m} از ۱۰۰**")

    grade = ""
    risk_pct = 0.0
    action = ""
    show_m4 = False
    can_proceed = False

    if total_score_3m >= 80:
        grade = "A+ (عالی - Set & Forget)"
        risk_pct = 1.0
        action = "ورود مستقیم (Set & Forget / Limit Order). کیفیت ستاپ عالی است."
        st.success(f"🔥 نتیجه: رتبه **{grade}** | ریسک مجاز: **{risk_pct}%**")
        st.success(f"✅ {action}")
        can_proceed = True
    elif total_score_3m < 60:
        grade = "معامله ممنوع (No Trade)"
        risk_pct = 0.0
        action = "❌ معامله لغو شد (امتیاز ۳ مرحله اول کمتر از ۶۰ است)."
        st.error(f"⛔ نتیجه: **{grade}**")
        st.warning(action)
        can_proceed = False
    else:
        st.warning("⚠️ امتیاز متوسط (۶۰ تا ۷۹). ورود مستقیم مجاز نیست!")
        st.warning("💡 برای دریافت مجوز ورود، در مرحله ۴ حداقل ۳۰ امتیاز از ۵۰ را کسب کنید.")
        show_m4 = True

    # =========================================================
    # MARHALE 4: TAIDIYE LTF
    # =========================================================
    score_m4 = 0
    if show_m4:
        st.markdown("---")
        st.subheader("📌 مرحله ۴: تأییدیه ورود در تایم پایین (LTF) و تایم زون (حداکثر ۵۰ امتیاز)")
        col_m4_1, col_m4_2 = st.columns(2)

        with col_m4_1:
            ltf_str_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("شکست با کلوز بدنه (BOS / MSS / CHoCH)", 12), "2": ("شکست صرفاً با سایه (Wick)", 5), "3": ("بدون شکست ساختار", 0)}
            ltf_str_sel = st.selectbox("۴.۱. شکست ساختار در تایم پایین (LTF)؟", list(ltf_str_opts.keys()), index=get_index_by_val(ltf_str_opts, loaded_data.get("4.1 Shekaste Sakhtar LTF")), format_func=lambda x: ltf_str_opts[x][0])
            score_m4 += ltf_str_opts[ltf_str_sel][1]
            details["4.1 Shekaste Sakhtar LTF"] = ltf_str_opts[ltf_str_sel][0]

            zone_patt_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("اینگلف / پوشای قدرتمند (Engulfing)", 8), "2": ("پین‌بار / چکش / شوتینگ استار", 8), "3": ("ستاره صبحگاهی / عصرگاهی", 6), "4": ("سایر الگوها", 4), "5": ("خیر", 0)}
            zone_patt_sel = st.selectbox("۴.۲. وضعیت الگوی کندلی تایم زون؟", list(zone_patt_opts.keys()), index=get_index_by_val(zone_patt_opts, loaded_data.get("4.2 Olgooye Candli Zone")), format_func=lambda x: zone_patt_opts[x][0])
            score_m4 += zone_patt_opts[zone_patt_sel][1]
            details["4.2 Olgooye Candli Zone"] = zone_patt_opts[zone_patt_sel][0]

            ltf_disp_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("جابه‌جایی پرقدرت (Displacement) + FVG واضح", 8), "2": ("بدون FVG / ضعیف", 1)}
            ltf_disp_sel = st.selectbox("۴.۳. وضعیت جابه‌جایی و FVG در تایم پایین؟", list(ltf_disp_opts.keys()), index=get_index_by_val(ltf_disp_opts, loaded_data.get("4.4 Displacement va FVG LTF")), format_func=lambda x: ltf_disp_opts[x][0])
            score_m4 += ltf_disp_opts[ltf_disp_sel][1]
            details["4.4 Displacement va FVG LTF"] = ltf_disp_opts[ltf_disp_sel][0]

        with col_m4_2:
            ltf_candle_power_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("بله، بدنه قوی‌تر و شادوها کوتاه‌تر (تسلط کامل)", 6), "2": ("متوسط", 3), "3": ("خیر، شادوها بلند", 0)}
            ltf_candle_power_sel = st.selectbox("۴.۴. تسلط کندل‌های موافق در LTF؟", list(ltf_candle_power_opts.keys()), index=get_index_by_val(ltf_candle_power_opts, loaded_data.get("4.5 Ghodrate Candle-haye Movafagh LTF")), format_func=lambda x: ltf_candle_power_opts[x][0])
            score_m4 += ltf_candle_power_opts[ltf_candle_power_sel][1]
            details["4.5 Ghodrate Candle-haye Movafagh LTF"] = ltf_candle_power_opts[ltf_candle_power_sel][0]

            ltf_lag_power_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("لگ‌های موافق قوی و پرشتاب‌تر", 6), "2": ("موازنه یکسان", 3), "3": ("لگ‌های موافق ضعیف‌تر", 0)}
            ltf_lag_power_sel = st.selectbox("۴.۵. وضعیت لگ‌های موافق در LTF؟", list(ltf_lag_power_opts.keys()), index=get_index_by_val(ltf_lag_power_opts, loaded_data.get("4.6 Vaziyate Lag-haye Movafagh LTF")), format_func=lambda x: ltf_lag_power_opts[x][0])
            score_m4 += ltf_lag_power_opts[ltf_lag_power_sel][1]
            details["4.6 Vaziyate Lag-haye Movafagh LTF"] = ltf_lag_power_opts[ltf_lag_power_sel][0]

            ltf_touch_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("برخورد و حرکت سریع (Touch & Go)", 5), "2": ("معطلی طولانی داخل زون", 1)}
            ltf_touch_sel = st.selectbox("۴.۶. رفتار قیمت داخل زون؟", list(ltf_touch_opts.keys()), index=get_index_by_val(ltf_touch_opts, loaded_data.get("4.7 Raftare Ghemat Daron Zone")), format_func=lambda x: ltf_touch_opts[x][0])
            score_m4 += ltf_touch_opts[ltf_touch_sel][1]
            details["4.7 Raftare Ghemat Daron Zone"] = ltf_touch_opts[ltf_touch_sel][0]

            ltf_sess_opts = {"0": ("-- انتخاب نشده --", 0), "1": ("سشن اصلی (لندن / نیویورک / هم‌پوشانی)", 5), "2": ("خارج از سشن اصلی", 1)}
            ltf_sess_sel = st.selectbox("۴.۷. سشن معاملاتی؟", list(ltf_sess_opts.keys()), index=get_index_by_val(ltf_sess_opts, loaded_data.get("4.8 Session Moamelati")), format_func=lambda x: ltf_sess_opts[x][0])
            score_m4 += ltf_sess_opts[ltf_sess_sel][1]
            details["4.8 Session Moamelati"] = ltf_sess_opts[ltf_sess_sel][0]

        st.info(f"📊 مجموع امتیاز تأییدیه مرحله ۴: **{score_m4} از ۵۰**")

        if score_m4 >= 30:
            grade = "B (خوب - با تأییدیه)"
            risk_pct = 0.65
            action = "مجوز ورود با تأییدیه تایم پایین صادر شد."
            st.success(f"✅ نتیجه: رتبه **{grade}** | ریسک مجاز: **{risk_pct}%**")
            can_proceed = True
        else:
            grade = "معامله ممنوع (تأییدیه ناموفق)"
            risk_pct = 0.0
            action = "❌ تأییدیه تایم پایین کافی نبود (امتیاز کمتر از ۳۰)."
            st.error(f"⛔ {action}")
            can_proceed = False

    # BUTTON: SAVE DRAFT
    st.markdown("---")
    col_draft, _ = st.columns([1, 1])
    with col_draft:
        if st.button("💾 ذخیره به عنوان پیش‌نویس تحلیل (نیمه‌کاره)", use_container_width=True):
            if not symbol:
                st.error("❌ لطفاً ابتدا نام نماد معاملاتی را وارد کنید.")
            else:
                details["Balance"] = loaded_data.get("Balance", None)
                details["Emtiyaze 3 Marhale"] = total_score_3m
                details["Grade"] = grade if grade else "Pishnevis"
                details["Darsade Risk"] = f"{risk_pct}%"
                details["Risk ($)"] = None
                details["Hajm (Lot)"] = None
                details["Vaziyat"] = "Pishnevis (Draft)"
                details["Noe TP / Khorooj"] = "Dar Hale Tahlil"
                details["Natijeh (PnL $)"] = None
                details["R:R Vaghei"] = None

                df_new = pd.DataFrame([details])
                if not df_all.empty and "Trade ID" in df_all.columns:
                    df_all = df_all[df_all["Trade ID"] != trade_id_val]
                    df_final = pd.concat([df_all, df_new], ignore_index=True)
                else:
                    df_final = df_new

                save_data(df_final)
                st.session_state["current_trade_id"] = generate_trade_id()
                st.success(f"📁 تحلیل با شناسه {trade_id_val} در فضای ابری ذخیره شد.")
                st.rerun()

    # POSITION ENTRY & LOT SIZE
    if can_proceed:
        st.markdown("---")
        st.subheader("💰 ورود به پوزیشن (محاسبه حجم معامله)")

        saved_balance = float(loaded_data.get("Balance", 10000.0)) if pd.notna(loaded_data.get("Balance")) else 10000.0

        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            balance = st.number_input("موجودی حساب (بالانس دلاری):", min_value=1.0, value=saved_balance, step=100.0)
        with col_p2:
            sl_pips = st.number_input("فاصله حد ضرر (Stop Loss) بر حسب پیپ:", min_value=0.1, value=15.0, step=1.0)
        with col_p3:
            pip_value_per_lot = st.number_input("ارزش دلاری هر پیپ برای ۱ لات:", min_value=0.01, value=10.0, step=0.5)

        risk_amount = balance * (risk_pct / 100)
        lot_size = ((risk_amount / (sl_pips * pip_value_per_lot)) if sl_pips > 0 and risk_pct > 0 and pip_value_per_lot > 0 else 0.0)

        st.metric("حجم معامله پیشنهادی (Lot Size)", f"{round(lot_size, 2)} لات")
        st.metric("میزان دلاری ریسک", f"${risk_amount:.2f}")

        if st.button("🚀 نهایی‌سازی تحلیل و ثبت معامله باز", use_container_width=True):
            if not symbol:
                st.error("❌ لطفاً ابتدا نماد معاملاتی را وارد کنید.")
            else:
                details["Balance"] = balance
                details["Emtiyaze 3 Marhale"] = total_score_3m
                details["Grade"] = grade
                details["Darsade Risk"] = f"{risk_pct}%"
                details["Risk ($)"] = risk_amount
                details["Hajm (Lot)"] = round(lot_size, 2)
                details["Vaziyat"] = "Baz (Open)"
                details["Noe TP / Khorooj"] = "Dar Intizar Khorooj"
                details["Natijeh (PnL $)"] = None
                details["R:R Vaghei"] = None

                df_new = pd.DataFrame([details])
                if not df_all.empty and "Trade ID" in df_all.columns:
                    df_all = df_all[df_all["Trade ID"] != trade_id_val]
                    df_final = pd.concat([df_all, df_new], ignore_index=True)
                else:
                    df_final = df_new

                save_data(df_final)
                st.session_state["current_trade_id"] = generate_trade_id()
                st.success(f"📁 معامله {trade_id_val} در فضای ابری ثبت شد.")
                st.rerun()

# =========================================================
# TAB 2: UPDATE CLOSED TRADE
# =========================================================
with tab2:
    st.title("📝 ثبت خروج، حد سود و مدیریت پوزیشن")
    df = load_data()

    if df.empty or "Vaziyat" not in df.columns:
        st.info("ℹ️ هنوز هیچ دیتایی در ژورنال ثبت نشده است.")
    else:
        open_trades = df[df["Vaziyat"] == "Baz (Open)"]
        if open_trades.empty:
            st.success("✅ هیچ معامله بازی برای بستن وجود ندارد.")
        else:
            st.subheader("📋 لیست معاملات باز")
            trades_dict = {
                f"[{idx}] شناسه: {row['Trade ID']} | نماد: {row['Namad']} | جهت: {row.get('Jahat (Buy/Sell)', '')} | تاریخ: {row['Tarikh']}": idx
                for idx, row in open_trades.iterrows()
            }
            selected_trade_str = st.selectbox("شماره ردیف معامله مورد نظر:", options=list(trades_dict.keys()))
            selected_idx = trades_dict[selected_trade_str]

            st.markdown("---")
            status_opts = {"1": ("بسته‌شده با سود یا زیان (Closed Trade)", "CLOSED"), "2": ("لغوشده / نرسیده به نقطه ورود", "CANCELED")}
            status_sel = st.radio("وضعیت نهایی معامله:", list(status_opts.keys()), format_func=lambda x: status_opts[x][0])
            status_code = status_opts[status_sel][1]

            if status_code == "CANCELED":
                if st.button("ثبت لغو معامله", use_container_width=True):
                    df.at[selected_idx, "Vaziyat"] = "Laghv-shode (Canceled/Missed)"
                    df.at[selected_idx, "Noe TP / Khorooj"] = "Nareside be Entry"
                    df.at[selected_idx, "Natijeh (PnL $)"] = 0.0
                    df.at[selected_idx, "R:R Vaghei"] = 0.0
                    save_data(df)
                    st.warning("❌ معامله لغو شد.")
                    st.rerun()
            else:
                exit_opts = {
                    "1": ("حد سود اول / خروج اسکالپ (۵۰٪ نقد + ریسک‌فری)", "TP1_SCALP"),
                    "2": ("حد سود دوم / تارگت اصلی (زون مقابل MTF)", "TP2_MAIN"),
                    "3": ("حد سود سوم / تارگت رانر (سقف/کف تایم بالا)", "TP3_RUNNER"),
                    "4": ("برخورد به حد ضرر (Stop Loss)", "SL_HIT"),
                    "5": ("خروج سر‌به‌سر / ریسک‌فری (Break Even)", "BREAK_EVEN"),
                }
                exit_sel = st.selectbox("نوع خروج:", list(exit_opts.keys()), format_func=lambda x: exit_opts[x][0])

                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    pnl_val = st.number_input("میزان سود یا زیان به دلار:", value=0.0, step=10.0)
                with col_c2:
                    rr_val = st.number_input("نسبت R:R به‌دست‌آمده:", value=0.0, step=0.1)

                if st.button("💾 ثبت نتیجه خروج", use_container_width=True):
                    df.at[selected_idx, "Vaziyat"] = "Baste-shode (Closed)"
                    df.at[selected_idx, "Noe TP / Khorooj"] = exit_opts[exit_sel][0]
                    df.at[selected_idx, "Natijeh (PnL $)"] = pnl_val
                    df.at[selected_idx, "R:R Vaghei"] = rr_val
                    save_data(df)
                    st.success("✅ نتیجه معامله در ابر ثبت شد.")
                    st.rerun()

# =========================================================
# TAB 3: SHOW JOURNAL STATS
# =========================================================
with tab3:
    st.title("📈 آمار کلی ژورنال ابری")
    df = load_data()

    if df.empty or "Vaziyat" not in df.columns:
        st.info("ℹ️ هنوز هیچ معامله‌ای ثبت نشده است.")
    else:
        closed_trades = df[df["Vaziyat"] == "Baste-shode (Closed)"]
        canceled_trades = len(df[df["Vaziyat"] == "Laghv-shode (Canceled/Missed)"])

        if closed_trades.empty:
            st.info("ℹ️ هنوز هیچ معامله بسته‌شده‌ای وجود ندارد.")
            st.metric("تعداد معاملات لغوشده", canceled_trades)
        else:
            total_closed = len(closed_trades)
            wins = len(closed_trades[closed_trades["Natijeh (PnL $)"] > 0])
            losses = len(closed_trades[closed_trades["Natijeh (PnL $)"] < 0])
            breakevens = len(closed_trades[closed_trades["Natijeh (PnL $)"] == 0])

            win_rate = (wins / total_closed) * 100 if total_closed > 0 else 0
            total_pnl = closed_trades["Natijeh (PnL $)"].sum()
            avg_rr = closed_trades["R:R Vaghei"].mean()

            c1, c2, c3 = st.columns(3)
            c1.metric("🎯 نرخ برد (Win Rate)", f"{win_rate:.1f}%")
            c2.metric("💵 سود/زیان کل (Total PnL)", f"${total_pnl:.2f}")
            c3.metric("📐 میانگین نسبت R:R", f"{avg_rr:.2f}")

            st.markdown("---")
            st.subheader("جزئیات آمار:")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("کل معاملات بسته‌شده", total_closed)
            m2.metric("برنده (Win)", wins)
            m3.metric("بازنده (Loss)", losses)
            m4.metric("سر‌به‌سر (Break Even)", breakevens)
            m5.metric("لغوشده (Canceled)", canceled_trades)

            st.markdown("---")
            st.subheader("📑 جدول داده‌های ابری در Google Sheets")
            st.dataframe(df, use_container_width=True)
