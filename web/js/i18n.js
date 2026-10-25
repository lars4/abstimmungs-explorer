const DICT = {
  de: {
    title: 'Abstimmungs-Explorer',
    tagline: 'Eidgenössische Volksabstimmungen nach Kanton und Gemeinde – mit Verlauf über die Zeit.',
    nav_votes: 'Abstimmungen', nav_trends: 'Verlauf', nav_about: 'Quellen',
    demo_banner: 'Demo-Daten: Die angezeigten Ergebnisse sind synthetisch und nicht real. Mit „python -m pipeline.build live“ werden echte BFS-Daten geladen.',
    search: 'Suchen (Titel, Datum) …', from: 'Von', to: 'Bis', all: 'Alle',
    outcome: 'Ergebnis', accepted: 'Angenommen', rejected: 'Abgelehnt', kind: 'Art',
    initiative: 'Initiative', referendum: 'Referendum', counter: 'Gegenvorschlag',
    yes: 'Ja', turnout: 'Beteiligung', cantons_yes: 'Kantone mit Ja', votes_found: 'Abstimmungen',
    national: 'Schweiz', back: '← Zurück zur Liste', canton_map: 'Kantone (Ja-Anteil)',
    legend_no: 'Nein', legend_yes: 'Ja', rank: 'Rangliste der Kantone', by_yes: 'nach Ja-Anteil', by_delta: 'nach Abweichung',
    municipalities: 'Gemeinden', pick_canton: 'Kanton wählen, um Gemeinden zu sehen', no_muni: 'Für diesen Kanton liegen keine Gemeindedaten vor.',
    muni_hint: 'Höchste und tiefste Ja-Anteile', highest: 'Höchster Ja-Anteil', lowest: 'Tiefster Ja-Anteil',
    trend_title: 'Verlauf nach Kanton', mode: 'Darstellung', mode_yes: 'Ja-Anteil', mode_delta: 'Abweichung vom Landesergebnis',
    smooth: 'Glätten (gleitender Schnitt)', topic: 'Themenfilter (Stichwort)', cantons: 'Kantone', national_line: 'Schweiz',
    about_title: 'Datenquellen & Lizenz', method_title: 'Hinweise zur Methodik',
    none: 'Keine Treffer.', municipality: 'Gemeinde', delta: 'Abw.', source_line: 'Quelle: Bundesamt für Statistik (BFS)',
    built: 'Datenstand', lang: 'Sprache', pp: 'pp', open_vote: 'Details',
  },
  en: {
    title: 'Vote Explorer',
    tagline: 'Swiss federal votes by canton and municipality – with trends over time.',
    nav_votes: 'Votes', nav_trends: 'Trends', nav_about: 'Sources',
    demo_banner: 'Demo data: the results shown are synthetic and not real. Run “python -m pipeline.build live” to load real FSO data.',
    search: 'Search (title, date) …', from: 'From', to: 'To', all: 'All',
    outcome: 'Outcome', accepted: 'Accepted', rejected: 'Rejected', kind: 'Type',
    initiative: 'Initiative', referendum: 'Referendum', counter: 'Counter-proposal',
    yes: 'Yes', turnout: 'Turnout', cantons_yes: 'Cantons in favour', votes_found: 'votes',
    national: 'Switzerland', back: '← Back to list', canton_map: 'Cantons (yes share)',
    legend_no: 'No', legend_yes: 'Yes', rank: 'Canton ranking', by_yes: 'by yes share', by_delta: 'by deviation',
    municipalities: 'Municipalities', pick_canton: 'Pick a canton to see its municipalities', no_muni: 'No municipality data for this canton.',
    muni_hint: 'Highest and lowest yes shares', highest: 'Highest yes share', lowest: 'Lowest yes share',
    trend_title: 'Trend by canton', mode: 'View', mode_yes: 'Yes share', mode_delta: 'Deviation from national result',
    smooth: 'Smooth (moving average)', topic: 'Topic filter (keyword)', cantons: 'Cantons', national_line: 'Switzerland',
    about_title: 'Data sources & licence', method_title: 'Methodology notes',
    none: 'No matches.', municipality: 'Municipality', delta: 'Dev.', source_line: 'Source: Federal Statistical Office (FSO)',
    built: 'Data as of', lang: 'Language', pp: 'pp', open_vote: 'Details',
  },
};

let lang = 'de';
try { lang = localStorage.getItem('lang') || (navigator.language || 'de').slice(0, 2); } catch { /* storage blocked */ }
if (!DICT[lang]) lang = 'de';

export const getLang = () => lang;
export function setLang(l) {
  lang = DICT[l] ? l : 'de';
  try { localStorage.setItem('lang', lang); } catch { /* ignore */ }
}
export const t = (k) => DICT[lang][k] ?? DICT.de[k] ?? k;
