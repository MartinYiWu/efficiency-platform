package com.aiep.aihub.domain.hr;

import java.time.*;
import java.util.*;

/** natural-months-1：首尾自然月均计入，年精度使用必然/可能区间分别求并集。 */
public final class HrMonthIntervalCalculator {
    public record DateRange(YearMonth earliest,YearMonth latest) {
        public DateRange { Objects.requireNonNull(earliest);Objects.requireNonNull(latest);if(earliest.isAfter(latest)) throw new IllegalArgumentException("date range reversed"); }
    }
    /** current必须来自明确“至今”；internship为null表示身份待核验。 */
    public record WorkPeriod(DateRange start,DateRange end,boolean current,Boolean internship) {
        public WorkPeriod { Objects.requireNonNull(start); if(current&&end!=null) throw new IllegalArgumentException("current end conflict"); }
    }
    public record MonthBounds(long minMonths,long maxMonths,boolean needsReview) {}
    private record Interval(long start,long end) {}
    public MonthBounds calculate(List<WorkPeriod> periods,LocalDate asOfDate) {
        long cap=YearMonth.from(asOfDate).getLong(java.time.temporal.ChronoField.PROLEPTIC_MONTH);
        List<Interval> certain=new ArrayList<>(),possible=new ArrayList<>(); boolean review=false;
        for(WorkPeriod period:periods) {
            if(Boolean.TRUE.equals(period.internship())) continue;
            if(period.internship()==null) { review=true;continue; }
            if(!period.current()&&period.end()==null) { review=true;continue; }
            long startMin=month(period.start().earliest()),startMax=month(period.start().latest());
            long endMin=period.current()?cap:Math.min(month(period.end().earliest()),cap);
            long endMax=period.current()?cap:Math.min(month(period.end().latest()),cap);
            if(startMin>endMax) { review=true;continue; }
            // 先去除不满足起点≤终点的日期组合，再取安全交集和并集。
            startMax=Math.min(startMax,endMax); endMin=Math.max(endMin,startMin);
            possible.add(new Interval(startMin,endMax+1));
            if(startMax<=endMin) certain.add(new Interval(startMax,endMin+1));
        }
        return new MonthBounds(union(certain),union(possible),review);
    }
    private long month(YearMonth date) { return date.getLong(java.time.temporal.ChronoField.PROLEPTIC_MONTH); }
    private long union(List<Interval> intervals) {
        intervals.sort(Comparator.comparingLong(Interval::start)); long sum=0,start=0,end=0; boolean first=true;
        for(Interval interval:intervals) {
            if(first) { start=interval.start();end=interval.end();first=false;continue; }
            if(interval.start()>end) { sum+=end-start;start=interval.start(); }
            end=Math.max(end,interval.end());
        }
        return first?0:sum+end-start;
    }
}
