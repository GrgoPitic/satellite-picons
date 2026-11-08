"""Compare local Skylink references with an uploaded Vhannibal lamedb v4."""
import io
import zipfile


def compare(blob, channels):
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        files = [x for x in archive.infolist() if x.filename.rsplit('/', 1)[-1] == 'lamedb']
        if len(files) != 1 or files[0].file_size > 20_000_000:
            raise ValueError('ZIP musí obsahovať jeden lamedb do 20 MB.')
        text = archive.read(files[0]).decode('utf-8-sig', errors='replace')
        source = files[0].filename
    lines = text.splitlines()
    if not lines or lines[0].strip() != 'eDVB services /4/':
        raise ValueError('Podporovaný je Enigma2 lamedb verzie 4.')
    try:
        begin = lines.index('services') + 1
        end = lines.index('end', begin)
    except ValueError:
        raise ValueError('Neúplná sekcia services v lamedb.')
    records = lines[begin:end]
    if len(records) % 3:
        raise ValueError('Poškodené záznamy služieb v lamedb.')
    services = {}
    for i in range(0, len(records), 3):
        p = records[i].split(':')
        if len(p) < 6:
            raise ValueError('Neplatný záznam služby.')
        sid, ns, tid, nid = [int(v, 16) for v in p[:4]]
        stype = int(p[4])
        services[(sid, tid, nid, ns)] = (records[i+1], f'1:0:{stype:X}:{sid:X}:{tid:X}:{nid:X}:{ns:X}:0:0:0:')
    result = []
    for channel in channels:
        if channel.get('provider_group') not in {'skylink-sk', 'skylink-cz'}:
            continue
        ref = str(channel.get('service_reference') or '')
        try:
            key = tuple(int(v,16) for v in ref.split(':')[3:7])
        except ValueError:
            key = ()
        found = services.get(key)
        result.append({'name':channel['name'], 'provider':channel['provider_group'], 'reference':ref,
                       'source_name':found[0] if found else None, 'source_reference':found[1] if found else None,
                       'status':'zhoda' if found else 'nenájdené'})
    if not services:
        raise ValueError('Settings neobsahujú služby.')
    return {'source':source,'services':len(services),'matched':sum(x['status']=='zhoda' for x in result),'channels':result}


def register(app, load_channels):
    from flask import request, jsonify
    @app.post('/api/vhannibal/check')
    def check():
        upload = request.files.get('settings')
        if not upload:
            return jsonify(error='Vyber Vhannibal ZIP settings.'), 400
        blob = upload.stream.read(10_000_001)
        if len(blob)>10_000_000:
            return jsonify(error='ZIP môže mať najviac 10 MB.'),400
        try:
            rows,_ = load_channels()
            return jsonify(compare(blob, rows))
        except (ValueError, zipfile.BadZipFile, KeyError, UnicodeError) as exc:
            return jsonify(error=str(exc)),400
