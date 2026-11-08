# Záväzný vzhľad piconov

Potvrdený štandard: pôvodná šablóna `assets/templates/piconblack-150x90.png`, PNG 150 × 90 pixelov. Šablónu zachovať bez zmeny.

Logo je vycentrované, zachováva pomer strán a zmestí sa do plochy 148 × 86 px. Optické zväčšenie, zosvetlenie tmavých častí a čistenie okrajov sú vedomé úpravy správcu. Zdrojové logá sa automaticky nenahrádzajú obrázkami od externých poskytovateľov.

Náhľad administrácie aj build používajú rovnaký renderer `scripts/build.py`. Nové rozhrania musia tento renderer opätovne použiť, nie vytvárať vlastnú interpretáciu vzhľadu.

## Jediná cesta publikovania

Lokálna správa → zdrojové logá a priradenia v GitHube → build z main → GitHub Pages → webový katalóg a klienti OpenPLi/Enigma2.

Pracovná vetva slúži na prípravu a kontrolu. Verejné balíky sa menia až úspešným zostavením a nasadením main. GitHub je spoločný zdroj verziovaných podkladov; GitHub Pages poskytuje výsledné PNG a ZIP balíky.

Budúci Enigma2 plugin načíta `version.json` a `providers.json` z rovnakého webu ako existujúci aktualizátor. Stiahne hotové balíky; nebude kresliť logá ani meniť šablónu. Zmenu nainštalovanej verzie zaznamená až po úspešnej inštalácii. Lokálna správa nemá automaticky prepisovať neuložené úpravy pri sťahovaní zmien z GitHubu.

Skylink: importovať celý príslušný Vhannibal bouquet bez filtrovania krajiny alebo jazyka. Synchronizácia mení katalóg a service reference, nie pôvodnú šablónu piconblack.
