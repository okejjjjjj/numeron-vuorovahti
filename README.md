<img width="40%"  alt="9652" src="https://github.com/user-attachments/assets/4c9c827d-6053-4240-aeea-1ba6f3194ece" />
<img width="40%" alt="9651" src="https://github.com/user-attachments/assets/e512a8dd-0e6a-4037-98d9-995977097590" />

# Numeron-vuorovahti

Moderni ja kevyt Android-sovellus Numeron WFM -työaikaseurantaan. Numeron-vuorovahti automatisoi työaikaleimaukset, synkronoi työvuorot ja lomat saumattomasti Google Kalenteriin sekä tekee vuorojen hallinnasta vaivatonta.

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
1. **Organisaation osoitteen** (esim. `omaorganisaatio.numeronwfm.com`)
2. **Käyttäjätunnuksen ja salasanan**
3. **Automaattisen synkronoinnin** asetukset
4. **Kohdekalenterin** (voit valita haluamasi puhelimen kalenterin pudotusvalikosta)
5. **Leimausmuistutukset**
