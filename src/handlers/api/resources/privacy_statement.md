# Privacyverklaring UBBC Bot

_Laatst bijgewerkt: 2026-11-02_

De UBBC Bot is een Telegram-bot waarmee leden van UBBC gezamenlijk bier
bestellen. Deze verklaring legt uit welke persoonsgegevens de bot verwerkt,
waarom, hoe lang, en welke rechten je hebt. De verwerking valt onder de
Algemene Verordening Gegevensbescherming (AVG).

## Verwerkingsverantwoordelijke

De verwerkingsverantwoordelijke is het bedrijf dat handelt onder de naam
Utrecht Beer Buyers Club (UBBC):

- **Bedrijf:** Kitano ICT (handelsnaam: Utrecht Beer Buyers Club, UBBC)
- **Adres:** Weerschijnvlinder 16, 3544 DV Utrecht, Nederland
- **Telefoon:** +31 6 50691239
- **E-mail:** info [at] kitano [dot] nl
- **KVK:** 30197597
- **BTW:** NL001879397B69

## Welke gegevens we verwerken

Wanneer je de bot gebruikt, verwerken we:

| Gegeven | Herkomst | Doel |
|---|---|---|
| Telegram-gebruikers-ID | Telegram | Je herkennen en berichten kunnen sturen |
| Telegram-gebruikersnaam (@...) | Telegram | Identificatie en contact door de beheerder |
| Voornaam en achternaam | Telegram / door beheerder ingevoerd | Bestellingen en leveringen koppelen aan een persoon |
| Taalvoorkeur | Telegram | Berichten in de juiste taal tonen |
| Contactgegevens (optioneel) | Door beheerder ingevoerd | Contact bij gastgebruikers zonder Telegram |
| Bestel- en betaalgeschiedenis | Jouw gebruik van de bot | Bestellingen, levering, facturatie en tegoeden |

De ophaal-/leverlocatie die de bot gebruikt is een vaste, gedeelde locatie voor
de groep en is **geen** persoonsgegeven.

We verwerken **geen** bijzondere categorieën van persoonsgegevens.

## Doeleinden en grondslag

- **Uitvoeren van bestellingen en leveringen** (grondslag: uitvoering van de
  overeenkomst / gerechtvaardigd belang van de groep om samen in te kopen).
- **Betalingen en tegoeden bijhouden** (grondslag: uitvoering van de
  overeenkomst; voor zover een fiscale bewaarplicht geldt: wettelijke
  verplichting).
- **Meldingen over nieuwe aanbiedingen** — alleen als je je hebt aangemeld
  (grondslag: toestemming; je kunt je altijd afmelden met `/unsubscribe`).

## Zichtbaarheid in de groep

Bij een bestelling kan in de groepschat een melding verschijnen in de vorm
"Voornaam L. bestelde N× product". Je voornaam en eerste letter van je
achternaam zijn daarmee zichtbaar voor andere groepsleden.

## Ontvangers en verwerkers

- **Telegram** — voor het versturen en ontvangen van berichten.
- **Amazon Web Services (AWS)** — voor hosting en opslag (Lambda, DynamoDB, S3,
  Parameter Store). Gegevens worden opgeslagen in een AWS-regio binnen de EU.

We verkopen je gegevens niet en delen ze niet met andere derden voor
marketingdoeleinden.

## Bewaartermijn

- **Bestel- en transactiegeschiedenis:** maximaal 8 jaar in de
  productieomgeving (testomgeving: 90 dagen), waarna gegevens automatisch
  worden verwijderd. Deze termijn is gekozen om te voldoen aan de wettelijke
  fiscale bewaarplicht voor administratie en betaalgegevens.
- **Profielgegevens** worden bewaard zolang je account actief is en worden op
  verzoek verwijderd of geanonimiseerd (zie hieronder).

## Jouw rechten

Je hebt het recht op inzage, correctie, verwijdering ("recht op vergetelheid"),
beperking en bezwaar. Ook kun je je toestemming voor meldingen op elk moment
intrekken.

- **Afmelden voor meldingen:** stuur `/unsubscribe` naar de bot.
- **Inzage, correctie of verwijdering:** neem contact op via het adres
  hierboven. Bij verwijdering worden je identificeerbare gegevens gewist of
  gepseudonimiseerd; transactiegegevens kunnen in geanonimiseerde vorm bewaard
  blijven voor een correcte administratie.
- **Klacht:** je kunt een klacht indienen bij de Autoriteit Persoonsgegevens
  ([autoriteitpersoonsgegevens.nl](https://autoriteitpersoonsgegevens.nl)).

## Beveiliging

Gegevens worden versleuteld opgeslagen en de toegang is beperkt tot de beheerder
en de bot zelf, volgens het principe van minimale rechten. Secrets (zoals
tokens) worden apart en versleuteld bewaard.

## Wijzigingen

Deze verklaring kan worden aangepast als de werking van de bot verandert. De
datum bovenaan geeft de laatste wijziging aan.
