# Numeron vuorovahti

Moderni ja kevyt Android-sovellus Numeron WFM -työaikaseurantaan. Numeron vuorovahti automatisoi työaikaleimaukset, synkronoi työvuorot ja lomat saumattomasti Google Kalenteriin sekä tekee vuorojen hallinnasta vaivatonta.

## Tärkeimmät ominaisuudet

* **Dynaaminen organisaatiotuki:** Toimii millä tahansa Numeron WFM -alustalla. Voit syöttää oman organisaatiosi osoitteen tai tunnuksen helposti asetuksista.
* **Automaattinen kalenterisynkronointi:** Hakee tulevat työvuorot ja vuosilomat suoraan puhelimen Google Kalenteriin.
* **Älykkäät muistutukset ja pikaleimaus:** Ilmoittaa ennen vuoron alkua ja loppua. Ilmoituksessa on suora Leimaa sisään / ulos -painike, joka hoitaa leimauksen yhdellä napautuksella ilmoitusta suurentamatta.
* **Taustaseuranta:** Tarkistaa säännöllisesti uudet julkaistut työvuorolistat ja päivittää kalenterin automaattisesti taustalla.
* **Salattu tallennus:** Käyttäjätunnukset ja salasanat tallennetaan laitteistotasolla salattuun muistiin (`EncryptedSharedPreferences`).

## Teknologiat

* **Kieli:** Kotlin
* **Käyttöliittymä:** Material Design 3
* **Tietoturva & Biometria:** AndroidX Security Crypto

## Asetukset

Ensimmäisellä käynnistyskerralla sovellus pyytää määrittämään:
1. **Organisaation osoitteen tai tunnisteen** (esim. `omaorganisaatio.numeronwfm.com`)
2. **Numeron Käyttäjätunnuksen ja salasanan**
3. **Automaattisen synkronoinnin** asetukset
4. **Kohdekalenterin**
5. **Leimausmuistutukset**
