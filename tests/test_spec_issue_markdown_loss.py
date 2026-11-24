"""Black-box contract tests: the default Markdown renderer must not lose text.

``issue --markdown`` renders only ``renderedFields`` HTML. The shared converter
drops link and image destinations, which silently erased images without alt
text (their source was the only visible data) and the account names behind user
mentions. Every fixture below is a Jira-shaped HTML fragment; no HTTP request
is made and no credential is read.
"""

from atlawire.issue_markdown import render_issue_markdown


def _literal(markdown: str) -> str:
    """Drop Markdown backslash escapes: presentation only, not text."""
    return markdown.replace("\\", "")


def _render(description: str, *, comment_html: str | None = None) -> str:
    fields: dict[str, object] = {"summary": "Summary"}
    rendered_fields: dict[str, object] = {"description": description}
    if comment_html is not None:
        fields["comment"] = {"comments": [{"id": "101", "body": "raw comment"}]}
        rendered_fields["comment"] = {"comments": [{"id": "101", "body": comment_html}]}
    return render_issue_markdown(
        {"key": "DEMO-42", "fields": fields, "renderedFields": rendered_fields}
    )


def test_image_without_alt_text_keeps_its_source():
    # PLAT-2611: the description had a rendered image with no alt text, so the
    # only copy of its address vanished from --markdown without a warning.
    source = "https://jira.example/secure/attachment/38503/38503_image-2026-03-31.png"
    markdown = _render(
        f'<p>Before</p><p><img src="{source}" height="194" width="532" /></p>'
        "<p>After</p>"
    )

    assert "Before" in markdown
    assert source in _literal(markdown)
    assert "38503_image-2026-03-31.png" in _literal(markdown)
    assert "After" in markdown
    # A literal source is data, never an active Markdown image.
    assert "![" not in markdown


def test_image_alt_text_is_kept_without_becoming_a_destination():
    markdown = _render(
        '<p><img src="https://jira.example/attachment/1/diagram.png" '
        'alt="Deployment diagram" /></p>'
    )

    assert "Deployment diagram" in markdown
    assert "https://jira.example/attachment/1/diagram.png" not in markdown


def test_emoticon_image_without_alt_text_stays_visible():
    markdown = _render(
        '<p>Готово <img class="emoticon" '
        'src="https://jira.example/images/icons/emoticons/check.png" '
        'height="16" width="16" alt="" /> сегодня</p>'
    )

    assert "Готово" in markdown
    assert "images/icons/emoticons/check.png" in markdown
    assert "сегодня" in markdown


def test_attachment_preview_keeps_file_name_and_address():
    markdown = _render(
        '<p><a id="39616_thumb" '
        'href="https://jira.example/secure/attachment/39616/39616_screenshot-1.png" '
        'title="screenshot-1.png" file-preview-type="image">'
        '<img src="https://jira.example/secure/thumbnail/39616/_thumb_39616.png" '
        'role="presentation" /></a></p>'
    )

    assert "screenshot-1.png" in markdown
    assert (
        "https://jira.example/secure/attachment/39616/39616_screenshot-1.png"
        in _literal(markdown)
    )


def test_image_source_with_markdown_characters_stays_literal():
    markdown = _render('<p><img src="https://jira.example/a/(b)*c*.png" /></p>')

    assert "\\(b\\)\\*c\\*.png" in markdown


def test_user_mention_keeps_display_name_and_account_name():
    # The rendered label is a display name; the account name behind it is what
    # identifies the person and it used to be dropped with the link destination.
    markdown = _render(
        '<p><a href="https://jira.example/secure/ViewProfile.jspa?name=s.komarov" '
        'class="user-hover" rel="s.komarov">Svyatoslav Komarov</a> лог файла</p>'
    )

    assert "Svyatoslav Komarov (s.komarov)" in markdown
    assert "лог файла" in markdown


def test_user_mention_without_rel_uses_the_profile_query():
    markdown = _render(
        '<p><a href="https://jira.example/secure/ViewProfile.jspa?name=m.bessonov" '
        'class="user-hover">Maxim Bessonov</a></p>'
    )

    assert "Maxim Bessonov (m.bessonov)" in markdown


def test_user_mention_keeps_a_non_latin_account_name():
    markdown = _render('<p><a class="user-hover" rel="иван.петров">Иван Петров</a></p>')

    assert "Иван Петров (иван.петров)" in markdown


def test_plain_link_keeps_its_label_and_not_its_destination():
    markdown = _render(
        '<p>See <a href="https://jira.example/browse/PLAT-1">PLAT-1</a> and '
        '<a href="https://example.com/x">the site</a>.</p>'
    )

    assert "PLAT-1" in markdown
    assert "the site" in markdown
    assert "browse/PLAT-1" not in markdown


def test_table_keeps_every_cell_text():
    markdown = _render(
        '<table class="confluenceTable"><tbody>'
        "<tr><th>Направление</th><th>Проблема</th></tr>"
        "<tr><td>Мониторинг</td><td>Ошибки сервиса</td></tr>"
        "</tbody></table>"
    )

    assert "| Направление | Проблема |" in markdown
    assert "| Мониторинг | Ошибки сервиса |" in markdown


def test_panel_keeps_title_and_body():
    markdown = _render(
        '<div class="panel" style="background-color: #ffffce">'
        "<b>Внимание</b><br/>Текст панели</div>"
    )

    assert "**Внимание**" in markdown
    assert "Текст панели" in markdown


def test_colored_text_keeps_its_text():
    markdown = _render(
        '<p><span style="color: rgb(255,0,0);">SELECT</span> '
        '<font color="#00b8b8">login</font></p>'
    )

    assert "SELECT" in markdown
    assert "login" in markdown


def test_nested_lists_keep_items_and_depth():
    markdown = _render("<ul><li>outer<ul><li>inner</li></ul></li><li>second</li></ul>")

    assert "- outer\n  - inner\n- second" in markdown


def test_code_and_noformat_blocks_keep_content():
    markdown = _render(
        '<div class="code panel"><div class="codeContent">'
        '<pre class="code-java">class A {}</pre></div></div>'
        "<pre>plain noformat</pre>"
    )

    assert "class A {}" in markdown
    assert "plain noformat" in markdown
    assert markdown.count("```") == 4


def test_expand_macro_keeps_control_and_hidden_text():
    markdown = _render(
        '<div class="expand-container"><div class="expand-control">'
        '<span class="expand-control-text">Подробности</span></div>'
        '<div class="expand-content">скрытый текст</div></div>'
    )

    assert "Подробности" in markdown
    assert "скрытый текст" in markdown


def test_rendered_text_stays_inert():
    markdown = _render("<p>literal **bold** and [brackets] &lt;tag&gt;</p>")

    assert "\\*\\*bold\\*\\*" in markdown
    assert "\\[brackets\\]" in markdown
    assert "\\<tag\\>" in markdown


def test_rendered_comment_keeps_image_source():
    markdown = _render(
        "<p>Body</p>",
        comment_html=(
            "<p>Report</p>"
            '<img src="https://jira.example/secure/attachment/40057/'
            '40057_image-2026-10-01.png" />'
        ),
    )

    assert "Comment 1" in markdown
    assert "Report" in markdown
    assert "40057_image-2026-10-01.png" in _literal(markdown)
