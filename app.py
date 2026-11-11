import streamlit as st

# Cheat sheet: https://docs.streamlit.io/develop/quick-reference/cheat-sheet
# Streamlit emojis: https://streamlit-emoji-shortcodes-streamlit-app-gwckff.streamlit.app
# Emoji finder: https://emojifinder.com/

q1 = st.Page('pages/q1.py', title='What does flu look like?', icon='📈')
q2 = st.Page('pages/q2.py', title='How does flu vary?', icon='📐')
q3 = st.Page('pages/q3.py', title='Do flu trends follow a pattern?', icon='📊')
q4 = st.Page('pages/q4.py', title='Which years stand out?', icon='🎯')
q5 = st.Page('pages/q5.py', title='Is flu getting better or worse?', icon='📉')
q6 = st.Page('pages/q6.py', title='Do nearby states track together?', icon='🗺')
q7 = st.Page('pages/q7.py', title='Does Google Trends agree?', icon='⚖️')
q8 = st.Page('pages/q8.py', title='Have both moved in step?', icon='⏳️')
q9 = st.Page('pages/q9.py', title='Do search terms agree?', icon='🧩')
q10 = st.Page('pages/q10.py', title='Google Trends as a proxy?', icon='🔁')

pg = st.navigation({'Single time series': [q1, q2, q3, q4, q5, q6], 
                   'Multiple time series': [q7, q8, q9, q10]})

pg.run()