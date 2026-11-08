"""Station-oriented navigation for the curated local administrator."""
from pathlib import Path


def enhance(page: str) -> str:
    fragment = Path(__file__).with_name('station_dashboard.html').read_text(encoding='utf-8')
    page = page.replace('<nav class="nav">', '<nav class="nav"><button type="button" data-panel="stations">Moje stanice<small>logá a operátori na jednom mieste</small></button><button type="button" data-panel="missing">Chýbajúce logá<small>čo ešte treba doplniť</small></button><button type="button" data-panel="changes">Zmeny operátorov<small>nové · odstránené · upravené</small></button><button type="button" data-panel="vhannibal">Zmeny Vhannibal<small>čo sa zmenilo pri synchronizácii</small></button>')
    page = page.replace('<div class="workspace-inner">', '<div class="workspace-inner">' + fragment.split('<!-- SCRIPT -->')[0])
    return page.replace('</body>', fragment.split('<!-- SCRIPT -->')[1] + '</body>')
