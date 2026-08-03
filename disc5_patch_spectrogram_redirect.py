# disc5_patch_spectrogram_redirect.py
# Replaces the "Show query spectrogram" dialog with an in-app redirect to the Query tonal
# lines CSV download (spectrogram renderer disabled pending improvement - v1.2 decision).
# Refuses to run if the target block does not match exactly (stale-copy guard).
#
#   python disc5_patch_spectrogram_redirect.py <path\to\disc5_gui_app.py>
#
# Run once on the repo working copy and once on the VM bundle copy
# (...\dist\disc5_gui\_internal\disc5_gui_app.py).

import sys

OLD = '''        # spectrogram -> separate window (modal if available). Single deck-style query panel.
        if wav_path and os.path.exists(wav_path):
            def _render_spec_body():
                png = spectrogram_png(wav_path, Path(name).stem)
                st.image(png, use_container_width=True)
                b64 = base64.b64encode(png).decode()
                st.markdown(
                    f'<a href="data:image/png;base64,{b64}" target="_blank" '
                    f'style="color:#1f9e8f;font-weight:600;">\\u2197 Open full size in a new tab</a>',
                    unsafe_allow_html=True)
                st.download_button("Download PNG", png,
                                   file_name=f"disc5_spectrogram_{Path(name).stem}.png",
                                   mime="image/png", key="dl_spec_png", use_container_width=True)
                st.caption("TPSW-whitened LOFAR spectrogram; horizontal markers are the detected "
                           "tonal lines (the same lines the tonal score uses), labelled in Hz.")
            if hasattr(st, "dialog"):
                _spec_dialog = st.dialog("Query spectrogram \\u2014 LOFAR tonals")(_render_spec_body)
                if st.button("\\U0001f52c Show query spectrogram (tonals labelled)"):
                    _spec_dialog()
            else:
                with st.expander("\\U0001f52c Query spectrogram (tonals labelled)"):
                    _render_spec_body()
'''.replace('\\u2197', '\u2197').replace('\\u2014', '\u2014').replace('\\U0001f52c', '\U0001f52c')

NEW = '''        # spectrogram view disabled pending renderer improvement (v1.2) - the button now
        # points the user to the tonal-lines CSV export instead.
        if wav_path and os.path.exists(wav_path):
            if st.button("\\U0001f52c Show query spectrogram (tonals labelled)"):
                st.info("The spectrogram view is unavailable in this version. Use the "
                        "**Query tonal lines** download in the Downloads panel below to "
                        "inspect the detected tonals \\u2014 the frequency and strength of "
                        "every line the tonal score uses.")
'''.replace('\\U0001f52c', '\U0001f52c').replace('\\u2014', '\u2014')

OLD_HDR = ('#   - "Show query spectrogram" button: the TPSW LOFAR spectrogram with the '
           'detected tonal lines')
NEW_HDR = ('#   - "Show query spectrogram" button: disabled in v1.2 (renderer pending) - '
           'shows a pointer to the tonal-lines CSV download')


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python disc5_patch_spectrogram_redirect.py <disc5_gui_app.py>")
    path = sys.argv[1]
    t = open(path, encoding="utf-8").read()
    if NEW.strip() in t:
        raise SystemExit(f"{path}: already patched - nothing to do")
    if OLD not in t:
        raise SystemExit(f"{path}: spectrogram block does not match expected code - "
                         f"STALE OR DIVERGED COPY, do not patch blindly")
    if t.count(OLD) != 1:
        raise SystemExit(f"{path}: block not unique")
    t = t.replace(OLD, NEW)
    if OLD_HDR in t:
        t = t.replace(OLD_HDR, NEW_HDR)
    open(path, "w", encoding="utf-8").write(t)
    print(f"{path}: patched - spectrogram button now redirects to the tonal-lines CSV")


if __name__ == "__main__":
    main()
