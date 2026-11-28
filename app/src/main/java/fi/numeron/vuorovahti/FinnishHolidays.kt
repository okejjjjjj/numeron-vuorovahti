package fi.numeron.vuorovahti

import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters
import java.util.concurrent.ConcurrentHashMap

/**
 * Laskee Suomen viralliset arkipyhät sekä juhannus- ja jouluaaton paikallisesti
 * ilman verkkopyyntöjä (Gregoriaaninen Meeus/Jones/Butcher-pääsiäisalgoritmi).
 */
object FinnishHolidays {

    private val cache = ConcurrentHashMap<Pair<Int, Boolean>, Map<LocalDate, String>>()

    fun easterSunday(year: Int): LocalDate {
        val a = year % 19
        val b = year / 100
        val c = year % 100
        val d = b / 4
        val e = b % 4
        val f = (b + 8) / 25
        val g = (b - f + 1) / 3
        val h = (19 * a + b - d - g + 15) % 30
        val i = c / 4
        val k = c % 4
        val l = (32 + 2 * e + 2 * i - h - k) % 7
        val m = (a + 11 * h + 22 * l) / 451
        val month = (h + l - 7 * m + 114) / 31
        val day = ((h + l - 7 * m + 114) % 31) + 1
        return LocalDate.of(year, month, day)
    }

    fun getHolidaysForYear(year: Int, en: Boolean = false): Map<LocalDate, String> {
        return cache.getOrPut(year to en) {
            val easter = easterSunday(year)
            val midsummerDay = LocalDate.of(year, 6, 20)
                .with(TemporalAdjusters.nextOrSame(DayOfWeek.SATURDAY))
            val midsummerEve = midsummerDay.minusDays(1)
            val allSaintsDay = LocalDate.of(year, 10, 31)
                .with(TemporalAdjusters.nextOrSame(DayOfWeek.SATURDAY))

            linkedMapOf(
                LocalDate.of(year, 1, 1) to (if (en) "New Year's Day" else "Uudenvuodenpäivä"),
                LocalDate.of(year, 1, 6) to (if (en) "Epiphany" else "Loppiainen"),
                easter.minusDays(2) to (if (en) "Good Friday" else "Pitkäperjantai"),
                easter to (if (en) "Easter Sunday" else "Pääsiäispäivä"),
                easter.plusDays(1) to (if (en) "Easter Monday" else "2. pääsiäispäivä"),
                LocalDate.of(year, 5, 1) to (if (en) "May Day" else "Vappu"),
                easter.plusDays(39) to (if (en) "Ascension Day" else "Helatorstai"),
                easter.plusDays(49) to (if (en) "Pentecost" else "Helluntaipäivä"),
                midsummerEve to (if (en) "Midsummer Eve" else "Juhannusaatto"),
                midsummerDay to (if (en) "Midsummer Day" else "Juhannuspäivä"),
                allSaintsDay to (if (en) "All Saints' Day" else "Pyhäinpäivä"),
                LocalDate.of(year, 12, 6) to (if (en) "Independence Day" else "Itsenäisyyspäivä"),
                LocalDate.of(year, 12, 24) to (if (en) "Christmas Eve" else "Jouluaatto"),
                LocalDate.of(year, 12, 25) to (if (en) "Christmas Day" else "Joulupäivä"),
                LocalDate.of(year, 12, 26) to (if (en) "Boxing Day" else "Tapaninpäivä")
            )
        }
    }

    fun getHolidayName(date: LocalDate, en: Boolean = false): String? {
        return getHolidaysForYear(date.year, en)[date]
    }
}
