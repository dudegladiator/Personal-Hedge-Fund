import streamlit as st
import pandas as pd
import time

from src.agents.fundamental_agent import fundamental_agent
from src.agents.sentimental_agent import sentimental_agent
from src.agents.backtesting_agent import backtesting_agent
from src.data_source.apis_3 import search_tickertape_stocks
from src.data_source.apis_1 import get_live_price
from page.reuse_component import render_stock_details_popup


def display_recommendation(title, recommendation, confidence, rationale=None, color_map=None):
    """Safely displays recommendation, confidence, and optional rationale."""
    try:
        if color_map is None:
            color_map = {"BULLISH": "green", "BEARISH": "red", "NEUTRAL": "orange"}

        recommendation_str = recommendation if recommendation else "N/A"
        color = color_map.get(recommendation, "grey")

        st.markdown(f"<{('h4' if title else 'h5')} style='color:{color};'>{title+': ' if title else ''}{recommendation_str}</{('h4' if title else 'h5')}>", unsafe_allow_html=True)

        if isinstance(confidence, (int, float)):
            normalized_confidence = confidence / 100.0 if confidence > 1 else confidence
            if 0 <= normalized_confidence <= 1:
                st.progress(normalized_confidence, text=f"Confidence: {confidence:.2f}{'%' if confidence > 1 else ''}")
            else:
                st.caption(f"Confidence: {confidence:.2f}")
        elif confidence is not None:
            st.caption(f"Confidence: {confidence}")

        if rationale:
            st.markdown("**Rationale / Overview:**")
            st.markdown(str(rationale))
    except Exception as e:
        st.warning(f"Error displaying recommendation element: {e}")


def initialize_stock_research_session():
    defaults = {
        'stock_research_query': "",
        'stock_search_results': None,
        'selected_stock_for_analysis': None,
        'stock_analysis_results': None,
        'analyze_button_clicked': False,
        'stock_research_force_analysis': False,
        'stock_research_refresh_days': 7,
        'stock_research_sentiment_days_news': 14,
        'stock_research_sentiment_days_announce': 90,
        'stock_research_backtesting_days': 365
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_selected_stock(stock_data):
    """Callback to set the selected stock and trigger analysis flag."""
    if isinstance(stock_data, dict) and "Ticker" in stock_data and "Name" in stock_data:
        st.session_state.selected_stock_for_analysis = stock_data
        st.session_state.analyze_button_clicked = True
        st.session_state.stock_analysis_results = None
    else:
        st.error("Invalid stock data received for analysis.")


def clear_selection_and_results():
    """Clears selection and results, e.g., when searching again."""
    st.session_state.selected_stock_for_analysis = None
    st.session_state.analyze_button_clicked = False
    st.session_state.stock_analysis_results = None
    st.session_state.stock_search_results = None
    
    
# --- Main Stock Research Rendering Function ---
def render_stock_research():
    st.title("🔍 Stock Research")
    try:
        initialize_stock_research_session()

        st.subheader("1. Find Stock")
        search_col1, search_col2 = st.columns([4, 1])
        with search_col1:
            search_term = st.text_input(
                "Enter Stock Name or Ticker:",
                value=st.session_state.stock_research_query,
                key="stock_research_input",
                placeholder="e.g., Reliance, INFY, Tata Motors",
                label_visibility='collapsed'
            )
        with search_col2:
            if st.button("Search", key="stock_research_search_button", use_container_width=True):
                st.session_state.stock_research_query = search_term.strip()
                clear_selection_and_results()
                st.rerun()

        with st.expander("Analysis Parameters", expanded=False):
            st.session_state.stock_research_force_analysis = st.checkbox(
                "Force Re-analysis (ignore cache)", value=st.session_state.stock_research_force_analysis,
                key="research_force_cb", help="Check this to ignore cached data."
            )
            cols_params = st.columns(3)
            with cols_params[0]:
                st.session_state.stock_research_refresh_days = st.number_input(
                    "Fundamental Cache (days)", min_value=1, max_value=30, value=st.session_state.stock_research_refresh_days,
                    step=1, key="research_fund_days", help="Fundamental data cache age."
                )
            with cols_params[1]:
                st.session_state.stock_research_sentiment_days_news = st.number_input(
                    "Sentiment News Lookback (days)", min_value=7, max_value=180, value=st.session_state.stock_research_sentiment_days_news,
                    step=1, key="research_sent_news_days", help="Past news days."
                )
                st.session_state.stock_research_sentiment_days_announce = st.number_input(
                    "Sentiment Announce Lookback (days)", min_value=7, max_value=365, value=st.session_state.stock_research_sentiment_days_announce,
                    step=1, key="research_sent_announce_days", help="Past announcement days."
                )
            with cols_params[2]:
                st.session_state.stock_research_backtesting_days = st.number_input(
                    "Backtesting Period (days)", min_value=30, max_value=1825, value=st.session_state.stock_research_backtesting_days,
                    step=1, key="research_backtest_days", help="Backtesting data period."
                )

        if st.session_state.stock_research_query and not st.session_state.selected_stock_for_analysis:
            query = st.session_state.stock_research_query
            st.markdown("---")
            st.subheader(f"2. Select Stock to Analyze")
            st.markdown(f"#### Search Results for: \"{query}\"")

            try:
                with st.spinner(f"Searching for '{query}'..."):
                    if st.session_state.stock_search_results is None:
                        st.session_state.stock_search_results = search_tickertape_stocks(query, limit=10)
                search_results = st.session_state.stock_search_results
            except Exception as api_err:
                st.error(f"Error calling stock search API: {api_err}")
                search_results = None



            # Display logic remains largely the same, but check search_results first
            if search_results is None:
                st.warning("Stock search could not be completed due to an error.")
            elif not search_results:
                st.info(f"No NSE stock results found matching \"{query}\".")
            else:
                st.caption("Click 'Analyze' on a stock below. Analysis uses parameters above.")
                results_cols = st.columns(2)
                col_idx = 0
                for i, stock in enumerate(search_results):
                    if isinstance(stock, dict):
                        with results_cols[col_idx % 2]:
                            with st.container(border=True, height=180):
                                try:
                                    change_pct = stock.get('Change %', 0.0)
                                    color = "green" if change_pct > 0 else ("red" if change_pct < 0 else "grey")
                                    ticker = stock.get('Ticker', 'N/A')
                                    name = stock.get('Name', 'Unknown Name')

                                    st.markdown(f"**{ticker}**")
                                    st.caption(f"{name}")
                                    st.caption(f"Price: ₹{stock.get('Price', 0.0):,.2f} (<span style='color:{color};'>{change_pct:+.2f}%</span>)", unsafe_allow_html=True)

                                    stock_data_for_analysis = {"Ticker": ticker, "Name": name}
                                    st.button(f"Analyze {ticker}", key=f"analyze_{ticker}_{i}",
                                            on_click=set_selected_stock, args=(stock_data_for_analysis,),
                                            use_container_width=True, type="primary")
                                except Exception as item_err:
                                    st.warning(f"Error displaying stock item: {item_err}")
                        col_idx += 1
                    else:
                        st.warning(f"Received invalid stock data format in search results: {stock}")
                st.markdown("---")

        selected_stock_info = st.session_state.selected_stock_for_analysis
        if selected_stock_info:
            if not isinstance(selected_stock_info, dict) or 'Ticker' not in selected_stock_info:
                st.error("Invalid selected stock data. Please search and select again.")
                st.session_state.selected_stock_for_analysis = None
                st.rerun()
                return

            ticker_to_analyze = selected_stock_info['Ticker']
            stock_name_to_analyze = selected_stock_info.get('Name', ticker_to_analyze)

            st.subheader(f"3. AI Analysis Results for: {stock_name_to_analyze} ({ticker_to_analyze})")

            should_run_analysis = st.session_state.analyze_button_clicked and \
                                (st.session_state.stock_analysis_results is None or st.session_state.stock_research_force_analysis)

            if should_run_analysis:
                force = st.session_state.stock_research_force_analysis
                fund_days = st.session_state.stock_research_refresh_days
                sent_news_days = st.session_state.stock_research_sentiment_days_news
                sent_announce_days = st.session_state.stock_research_sentiment_days_announce
                backtest_days = st.session_state.stock_research_backtesting_days

                with st.spinner(f"Performing AI analysis for {ticker_to_analyze}..."):
                    st.caption(f"Params: Force={force}, Fund Cache={fund_days}d, News={sent_news_days}d, Announce={sent_announce_days}d, Backtest={backtest_days}d")
                    analysis_results = {}
                    run_success = True

                    # --- Wrap the entire agent execution sequence ---
                    try:
                        st.write("Running Sentimental Analysis...")
                        analysis_results['sentimental'] = sentimental_agent(
                            symbol=ticker_to_analyze, exchange="nse", force=force,
                            past_days_for_news=sent_news_days, past_days_for_announcements=sent_announce_days
                        )
                        if not isinstance(analysis_results.get('sentimental'), dict):
                            st.warning("Sentimental agent returned unexpected format.")
                            analysis_results['sentimental'] = {"error": True, "message": "Unexpected result format."}

                        st.write("Running Fundamental Analysis...")
                        analysis_results['fundamental'] = fundamental_agent(
                            symbol=ticker_to_analyze, exchange="nse", force=force, refresh_days=fund_days
                        )
                        if not isinstance(analysis_results.get('fundamental'), dict):
                            st.warning("Fundamental agent returned unexpected format.")
                            analysis_results['fundamental'] = {"error": True, "message": "Unexpected result format."}

                        st.write("Running Backtesting Analysis...")
                        try:
                            analysis_results['backtesting'] = backtesting_agent(
                                symbol=ticker_to_analyze, exchange="nse", force=force, backtesting_days=backtest_days
                            )
                            if not isinstance(analysis_results.get('backtesting'), dict):
                                st.warning("Backtesting agent returned unexpected format.")
                                analysis_results['backtesting'] = {"error": True, "details": "Unexpected result format."}

                        except ImportError as ie:
                            st.error(f"Backtesting analysis failed: Library missing ({ie}). Install 'ta-lib-bin'.")
                            analysis_results['backtesting'] = {"error": True, "details": f"ImportError: {ie}"}
                        except Exception as e_bt:
                            st.error(f"Backtesting analysis error: {e_bt}")
                            analysis_results['backtesting'] = {"error": True, "details": str(e_bt)}
                            if "talib" in str(e_bt).lower():
                                st.warning("TA-Lib might be missing/misconfigured.")

                    except Exception as agent_exec_err:
                        st.error(f"A critical error occurred during agent execution: {agent_exec_err}")
                        st.session_state.stock_analysis_results = {"error": True, "message": f"Agent execution failed: {agent_exec_err}"}
                        run_success = False

                    finally:
                        if run_success:
                            st.session_state.stock_analysis_results = analysis_results
                            st.success(f"Analysis sequence completed for {ticker_to_analyze}.")
                            time.sleep(0.5)
                        st.session_state.analyze_button_clicked = False
                        if run_success:
                            st.rerun()
            # --- End Analysis Run Logic ---


            # --- Display Analysis Results ---
            results = st.session_state.stock_analysis_results
            if results:
                if results.get("error") and not any(k in results for k in ['sentimental', 'fundamental', 'backtesting']):
                    st.error(f"Analysis could not be displayed: {results.get('message', 'Unknown error')}")
                    return

                st.divider()
                st.subheader("📊 Sentimental Analysis")
                sentimental_results = results.get('sentimental')
                if sentimental_results is None:
                    st.info("Sentimental analysis data unavailable.")
                elif not isinstance(sentimental_results, dict):
                    st.warning("Invalid format for sentimental results.")
                elif sentimental_results.get("error"):
                    st.error(f"Sentimental Analysis Error: {sentimental_results.get('message', 'Unknown')}")
                else:
                    try:
                        st.markdown("**Overall Sentiment Message:** " + str(sentimental_results.get('message', 'N/A')))
                        news_analysis = sentimental_results.get("news_analysis", {})
                        announce_analysis = sentimental_results.get("announcement_analysis", {})

                        senti_cols = st.columns(2)
                        with senti_cols[0]:
                            st.markdown("**News Sentiment**")
                            if isinstance(news_analysis, dict) and not news_analysis.get("error"):
                                display_recommendation(title="", recommendation=news_analysis.get("recommendation_sign"), 
                                                    confidence=news_analysis.get("recommendation_confidence_score"), 
                                                    rationale=news_analysis.get("analysis_overview"))
                            elif isinstance(news_analysis, dict) and news_analysis.get("error"):
                                st.warning(f"News analysis issue: {news_analysis.get('message', 'N/A')}")
                            else:
                                st.caption("No news analysis data.")
                        with senti_cols[1]:
                            st.markdown("**Announcements Sentiment**")
                            if isinstance(announce_analysis, dict) and not announce_analysis.get("error"):
                                display_recommendation(title="", recommendation=announce_analysis.get("recommendation_sign"), 
                                                    confidence=announce_analysis.get("recommendation_confidence_score"), 
                                                    rationale=announce_analysis.get("analysis_overview"))
                            elif isinstance(announce_analysis, dict) and announce_analysis.get("error"):
                                st.warning(f"Announcement issue: {announce_analysis.get('message', 'N/A')}")
                            else:
                                st.caption("No announcement data.")

                        raw_senti_news = news_analysis.get("raw_data", []) if isinstance(news_analysis, dict) else []
                        raw_senti_announce = announce_analysis.get("raw_data", {}) if isinstance(announce_analysis, dict) else {}
                        if raw_senti_news or raw_senti_announce:
                            with st.expander("Raw Sentiment Data"):
                                if raw_senti_news:
                                    st.markdown("**News Articles:**")
                                    st.json(raw_senti_news)
                                if raw_senti_announce:
                                    st.markdown("**Announcements:**")
                                    st.json(raw_senti_announce)
                    except Exception as display_err:
                        st.warning(f"Error displaying sentimental results: {display_err}")

                # --- Display Fundamental Analysis ---
                st.divider()
                st.subheader("📈 Fundamental Analysis")
                fundamental_results = results.get('fundamental')
                if fundamental_results is None:
                    st.info("Fundamental analysis data unavailable.")
                elif not isinstance(fundamental_results, dict):
                    st.warning("Invalid format for fundamental results.")
                elif fundamental_results.get("error"):
                    st.error(f"Fundamental Analysis Error: {fundamental_results.get('error', 'Unknown')}")
                else:
                    try:
                        exec_summary = fundamental_results.get('executive_summary', {})
                        if isinstance(exec_summary, dict):
                            display_recommendation(title="Overall Recommendation", 
                                                recommendation=exec_summary.get("overall_signal_recommendation"),
                                                confidence=exec_summary.get("overall_signal_recommendation_confidence_pct"),
                                                rationale=exec_summary.get("overall_health_assessment_summary"))
                            st.markdown("**Key Rationale Points:**")
                            rationale_points = exec_summary.get('key_rationale', [])
                            if rationale_points:
                                for point in rationale_points:
                                    st.markdown(f"- {point}")
                            else:
                                st.caption("No specific rationale points.")
                        else:
                            st.warning("Executive summary missing or invalid.")

                        detailed_analysis = fundamental_results.get('detailed_analysis', {})
                        if isinstance(detailed_analysis, dict) and detailed_analysis:
                            st.markdown("---")
                            st.markdown("**Detailed Category Analysis:**")
                            num_categories = len(detailed_analysis)
                            cat_cols = st.columns(num_categories) if num_categories > 0 else [st]
                            i = 0
                            for category, details in detailed_analysis.items():
                                if isinstance(details, dict):
                                    col_to_use = cat_cols[i % len(cat_cols)]
                                    with col_to_use:
                                        st.markdown(f"**{str(category).replace('_', ' ').title()}**")
                                        display_recommendation(title="Signal", 
                                                            recommendation=details.get('signal'),
                                                            confidence=details.get('confidence_pct'))
                                        st.caption(str(details.get('summary', '')))
                                i += 1

                        raw_data = fundamental_results.get('raw_data', {})
                        with st.expander("Raw Fundamental Data"):
                            if isinstance(raw_data, dict):
                                st.json(raw_data)
                            else:
                                st.warning("Raw data format is invalid.")
                    except Exception as display_err:
                        st.warning(f"Error displaying fundamental results: {display_err}")


                # --- Display Backtesting Analysis ---
                st.divider()
                st.subheader("⏱️ Backtesting Analysis")
                backtesting_results = results.get('backtesting')
                if backtesting_results is None:
                    st.info("Backtesting analysis data unavailable.")
                elif not isinstance(backtesting_results, dict):
                    st.warning("Invalid format for backtesting results.")
                elif backtesting_results.get("error"):
                    st.error(f"Backtesting Analysis Error: {backtesting_results.get('details', 'Unknown')}")
                else:
                    try:
                        bt_exec_summary = backtesting_results.get('executive_summary', {})
                        if isinstance(bt_exec_summary, dict):
                            display_recommendation(title="Overall Assessment",
                                                recommendation=bt_exec_summary.get("recommendation_sign"),
                                                confidence=bt_exec_summary.get("recommendation_confidence"),
                                                rationale=bt_exec_summary.get("overall_summary"))
                            st.markdown("**Key Observations:**")
                            observations = bt_exec_summary.get('key_observations', [])
                            if observations and isinstance(observations, list):
                                for obs in observations:
                                    st.markdown(f"- {obs}")
                            else:
                                st.caption("No specific observations.")
                        else:
                            st.warning("Backtesting summary missing or invalid.")

                        strategy_analysis_list = backtesting_results.get('detailed_analysis', [])
                        raw_bt_data_list = backtesting_results.get('raw_data', [])

                        if isinstance(strategy_analysis_list, list) and strategy_analysis_list:
                            st.markdown("---")
                            st.markdown("**Strategy Performance:**")
                            for i, strategy_data in enumerate(strategy_analysis_list):
                                if isinstance(strategy_data, dict):
                                    strategy_name = strategy_data.get('strategy_name', f"Strategy {i+1}")
                                    with st.expander(f"Strategy: {strategy_name}", expanded=(i==0)):
                                        display_recommendation(title="Signal",
                                                            recommendation=strategy_data.get('signal'),
                                                            confidence=strategy_data.get('confidence'))
                                        st.markdown("**Summary:**")
                                        st.caption(str(strategy_data.get('summary', '')))

                                        raw_metrics_data = None
                                        try:
                                            if isinstance(raw_bt_data_list, list):
                                                if i < len(raw_bt_data_list) and isinstance(raw_bt_data_list[i], dict) and raw_bt_data_list[i].get('strategy_name') == strategy_name:
                                                    raw_metrics_data = raw_bt_data_list[i].get('backtest_results')
                                                elif not raw_metrics_data:
                                                    found_raw = next((rd.get('backtest_results') for rd in raw_bt_data_list if isinstance(rd, dict) and rd.get('strategy_name') == strategy_name), None)
                                                    if found_raw:
                                                        raw_metrics_data = found_raw
                                        except Exception as find_metric_err:
                                            st.caption(f"Note: issue finding raw metrics ({find_metric_err})")

                                        if isinstance(raw_metrics_data, dict):
                                            metrics = raw_metrics_data
                                            st.markdown("**Key Metrics:**")
                                            m_cols = st.columns(3)
                                            def format_metric(value, suffix='%', decimals=2):
                                                try:
                                                    if isinstance(value, (int, float)):
                                                        return f"{value * 100 if suffix == '%' else value:.{decimals}f}{suffix if suffix else ''}"
                                                except:
                                                    pass
                                                return "N/A"

                                            m_cols[0].metric("Total Return", format_metric(metrics.get('total_returns'), suffix='%'))
                                            m_cols[1].metric("Sharpe Ratio", format_metric(metrics.get('sharpe_ratio'), suffix='', decimals=2))
                                            m_cols[2].metric("Max Drawdown", format_metric(metrics.get('max_drawdown'), suffix='%'))
                                            m_cols[0].metric("Win Rate", format_metric(metrics.get('win_rate'), suffix='%', decimals=1))
                                            m_cols[1].metric("Profit Factor", format_metric(metrics.get('profit_factor'), suffix='', decimals=2))
                                            m_cols[2].metric("Total Trades", f"{metrics.get('total_trades', 'N/A')}")
                                        else:
                                            st.caption("Detailed metrics not found.")
                                else:
                                    st.warning("Invalid strategy data format.")

                        if isinstance(raw_bt_data_list, list) and raw_bt_data_list:
                            with st.expander("Raw Backtesting Data"):
                                st.json(raw_bt_data_list)
                    except Exception as display_err:
                        st.warning(f"Error displaying backtesting results: {display_err}")

                st.divider()
                st.subheader(f"🛒 Paper Trade {ticker_to_analyze}")
                try:
                    with st.spinner(f"Fetching live price for {ticker_to_analyze}..."):
                        live_price_data = get_live_price(ticker_to_analyze)

                    if live_price_data and isinstance(live_price_data, dict) and live_price_data.get('ltp') is not None:
                        popup_stock_data = {
                            "Ticker": ticker_to_analyze,
                            "Name": stock_name_to_analyze,
                            "Price": live_price_data.get('ltp'),
                            "Change": live_price_data.get('percentChange', 0.0)
                        }
                        render_stock_details_popup(popup_stock_data)
                    else:
                        st.warning(f"Could not fetch valid live price data for {ticker_to_analyze} to enable trading actions.")
                except Exception as popup_err:
                    st.error(f"Error fetching price or rendering trade component: {popup_err}")

    except Exception as page_err:
        st.error(f"An unexpected error occurred on the Stock Research page: {page_err}")
        st.error("Please try refreshing the page or contact support if the issue persists.")