# Verwerkingsregister UBBC Bot

_Register van verwerkingsactiviteiten conform artikel 30 AVG. Laatst bijgewerkt:
2026-11-02._

Dit register beschrijft de verwerkingen van persoonsgegevens door de UBBC Bot.
De bijbehorende informatie voor betrokkenen staat in de
[privacyverklaring](privacy_statement.md).

## 1. Verwerkingsverantwoordelijke

- **Bedrijf:** Kitano ICT (handelsnaam: Utrecht Beer Buyers Club, UBBC)
- **Adres:** Weerschijnvlinder 16, 3544 DV Utrecht, Nederland
- **Telefoon:** +31 6 50691239
- **E-mail:** info [at] kitano [dot] nl
- **KVK:** 30197597
- **BTW:** NL001879397B69

## 2. Verwerkingsactiviteiten

### 2.1 Beheer van bestellingen en leveringen

| Onderdeel | Beschrijving |
|---|---|
| **Doel** | Leden in staat stellen samen bier te bestellen en leveringen te organiseren |
| **Grondslag** | Uitvoering van de overeenkomst / gerechtvaardigd belang van de groep |
| **Betrokkenen** | Leden (klanten) en gastgebruikers van UBBC |
| **Categorieën gegevens** | Telegram-ID, gebruikersnaam, voor- en achternaam, taalvoorkeur, optionele contactgegevens, bestelgeschiedenis |
| **Ontvangers** | Telegram (berichten), AWS (hosting/opslag) |
| **Bewaartermijn** | Profielgegevens zolang account actief; bestelgeschiedenis max. 5 jaar (prod) / 90 dagen (test), daarna automatische verwijdering (TTL) |

### 2.2 Betalingen en tegoeden

| Onderdeel | Beschrijving |
|---|---|
| **Doel** | Facturatie, registreren van betalingen en bijhouden van klanttegoeden |
| **Grondslag** | Uitvoering van de overeenkomst; waar van toepassing wettelijke (fiscale) bewaarplicht |
| **Betrokkenen** | Leden en gastgebruikers |
| **Categorieën gegevens** | Klant-ID, bedragen, betaal- en tegoedtransacties, tijdstippen |
| **Ontvangers** | AWS (opslag) |
| **Bewaartermijn** | Max. 5 jaar (prod); indien fiscale bewaarplicht geldt, zolang die vereist |

### 2.3 Meldingen over nieuwe aanbiedingen

| Onderdeel | Beschrijving |
|---|---|
| **Doel** | Geïnteresseerde leden informeren over nieuwe aanbiedingen |
| **Grondslag** | Toestemming (opt-in via `/subscribe`, intrekbaar via `/unsubscribe`) |
| **Betrokkenen** | Leden die zich hebben aangemeld |
| **Categorieën gegevens** | Telegram-ID, abonnementsstatus |
| **Ontvangers** | Telegram |
| **Bewaartermijn** | Tot intrekking van de toestemming of verwijdering van het account |

## 3. Verwerkers

| Verwerker | Rol | Locatie |
|---|---|---|
| Amazon Web Services (AWS) | Hosting en opslag (Lambda, DynamoDB, S3, Parameter Store) | EU-regio |
| Telegram | Verzenden en ontvangen van berichten | Zie Telegram-privacybeleid |

Met verwerkers behoren verwerkersovereenkomsten te zijn gesloten; AWS biedt
hiervoor een standaard Data Processing Addendum.

## 4. Doorgifte buiten de EER

Opslag vindt plaats in een AWS-regio binnen de EU. Telegram verwerkt berichten
mogelijk buiten de EER; dit is inherent aan het gebruik van Telegram als
communicatiekanaal.

## 5. Technische en organisatorische maatregelen

- Versleutelde opslag (DynamoDB/S3 encryptie) en versleutelde secrets in SSM.
- Toegang volgens minimale rechten (per functie afgebakende IAM-rechten).
- Validatie van binnenkomende webhooks (secret token).
- Beperkte toegang: alleen de beheerder en de bot.

## 6. Rechten van betrokkenen

Inzage, correctie, verwijdering, beperking, bezwaar en intrekken van
toestemming. Zie de [privacyverklaring](../src/handlers/api/privacyverklaring.md) voor de
procedure. Bij verwijdering worden identificeerbare gegevens gewist of
gepseudonimiseerd; transactiegegevens kunnen geanonimiseerd bewaard blijven.

## 7. Aandachtspunten / openstaand

- Een geautomatiseerde verwijder-/anonimiseerflow ("recht op vergetelheid") is
  nog niet geïmplementeerd; verwijdering gebeurt nu op verzoek, handmatig.
- Logs kunnen namen bevatten; het terugdringen hiervan staat op de planning.
