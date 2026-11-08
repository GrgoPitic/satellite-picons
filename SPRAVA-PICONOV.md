# Správa piconov a OpenPLi

## Každodenná práca

1. Spusti `admin.command`.
2. Vyber kanál vľavo a otvor **Nahrať logo**. Ulož svoj obrázok.
3. V **Upraviť logo** skontroluj vzhľad. V **Knižnici log** priraď logo k rovnakému kanálu u ďalších operátorov.
4. V **Publikovanie** vytvor lokálny náhľad a skontroluj výsledok.
5. Odošli uložené zmeny. Verejná stránka sa aktualizuje až po úspešnom GitHub Actions zostavení a nasadení vetvy `main`. Publikovanie inej vetvy nemení verejný balík.

Nahratie nového loga zachová existujúce priradenia operátorom. Odstránenie vlastnej úpravy kanála sa uloží lokálne; publikovanie spusti samostatne.

## Prijímač OpenPLi

Grafický plugin zostáva v `receiver/plugin/Plugins/Extensions/SatellitePicons`. Podporuje celý balík operátora, kanály z bouquetov a aktualizáciu existujúcich piconov. Táto verzia GUI ešte neplánuje automatické aktualizácie.

Na automatické aktualizácie slúži `receiver/update_picons.py`. Vyžaduje Python 3. Skopíruj ho napríklad do `/usr/local/bin/update_picons.py` v prijímači. Vyber skutočný priečinok piconov používaný skinom; nižšie je príklad `/media/hdd/picon`.

```sh
python3 /usr/local/bin/update_picons.py --list
python3 /usr/local/bin/update_picons.py --provider skylink-sk --dest /media/hdd/picon --check
python3 /usr/local/bin/update_picons.py --provider skylink-sk --dest /media/hdd/picon
```

Pre ANTIK použi `antik-sat-sk`. Po úspešnom stiahnutí si aktualizátor zapamätá verziu v cieľovom priečinku. Rovnakú verziu znova nesťahuje. Pri vymazaných alebo poškodených piconoch pridaj `--force`.

Ak má prijímač zapnutý cron, cez `crontab -e` pridaj napríklad dennú kontrolu o 04:15. Zachovaj existujúce riadky:

```cron
15 4 * * * /usr/bin/python3 /usr/local/bin/update_picons.py --provider skylink-sk --dest /media/hdd/picon
```

Over umiestnenie Pythonu cez `command -v python3`. Prijímač musí byť zapnutý a pripojený na internet. Kontroluje sa zverejnená verzia z webu projektu, nie každý commit v repozitári. Aktualizátor nahrádza jednotlivé súbory až po ich úplnom rozbalení. Celý balík nie je jedna transakcia; pri prerušení sa ďalší beh pokúsi dokončiť aktualizáciu. Staré názvy piconov automaticky nemaže.

Inštaláciu a cron treba overiť na konkrétnom prijímači. Táto úprava bola testovaná lokálne so simulovaným sťahovaním.
