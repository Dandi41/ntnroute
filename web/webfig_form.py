"""Draft-only WebFig checkbox interaction. Never submits or claims persistence.

Caller must reopen the saved object before read_checkbox can establish persisted
state. A successful draft change alone is not proof of device configuration.
"""


def _checkbox(page, label):
    if not isinstance(label, str) or not label.strip():
        raise ValueError('exact nonempty label required')
    rows = page.locator('#content tr').filter(
        has=page.locator('td.label').get_by_text(label, exact=True))
    visible = [rows.nth(i) for i in range(rows.count()) if rows.nth(i).is_visible()]
    if len(visible) != 1:
        raise ValueError('expected one visible labeled row')
    controls = visible[0].locator('input[type=checkbox]')
    if controls.count() != 1 or not controls.is_visible():
        raise ValueError('expected one visible checkbox')
    return controls


def read_checkbox(page, label):
    """Read explicit checked state; freshness/persistence is caller responsibility."""
    return _checkbox(page, label).is_checked()


def set_draft_checkbox(page, label, checked):
    """Use native Playwright interaction once, then re-resolve after DOM updates.

    No submit, force click, direct DOM assignment, or mutation retry. The short
    settle check detects local rerenders; it is not a persistence guarantee.
    """
    if type(checked) is not bool:
        raise ValueError('checked must be boolean')
    control = _checkbox(page, label)
    if not control.is_enabled():
        raise ValueError('checkbox is disabled')
    if control.is_checked() != checked:
        control.set_checked(checked, timeout=2000)
    for _ in range(3):
        page.wait_for_timeout(50)
        if read_checkbox(page, label) != checked:
            raise ValueError('draft checkbox state did not remain stable; no retry')
    return checked
