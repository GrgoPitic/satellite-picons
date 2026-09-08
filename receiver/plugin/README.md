# Satellite Picons – Enigma2 plugin

GUI klient pre spoločný provider katalóg používaný webom aj prijímačom.

## Funkcie

- načíta `providers.json` z rovnakého zdroja ako web
- zobrazí Skylink, ANTIK Sat a ďalšie platformy bez potreby meniť plugin
- OK / zelené tlačidlo otvorí možnosti vybratej platformy:
  - **Celý balík platformy**
  - **Len moje kanály (bouquety)** – porovná SRP identitu s `/etc/enigma2/userbouquet*.tv` a `*.radio`
  - **Aktualizovať iba existujúce picony** – prepíše len súbory, ktoré už v cieľovom picon priečinku existujú
- modré tlačidlo stiahne globálny balík
- žlté tlačidlo prepína cieľový picon priečinok
- sťahovanie a rozbaľovanie beží mimo GUI threadu

## Inštalačná cesta

```
/usr/lib/enigma2/python/Plugins/Extensions/SatellitePicons/
```

Toto je zdrojová vývojová verzia. IPK balenie a updater pluginu budú doplnené v ďalšej fáze.
