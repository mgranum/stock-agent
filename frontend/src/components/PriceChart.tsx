import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
} from "lightweight-charts";

import type { Candle } from "../types";

type Props = {
  candles: Candle[];
  showVolume: boolean;
  showSma20: boolean;
  showSma50: boolean;
};

export function PriceChart({ candles, showVolume, showSma20, showSma50 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      autoSize: true,
      height: 430,
      layout: {
        background: { type: ColorType.Solid, color: "#0b1730" },
        textColor: "#9fb0cd",
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: "#172746" },
        horzLines: { color: "#172746" },
      },
      rightPriceScale: { borderColor: "#263958" },
      timeScale: { borderColor: "#263958", timeVisible: true },
      crosshair: { vertLine: { color: "#5b8def" }, horzLine: { color: "#5b8def" } },
    });

    const priceSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c79a",
      downColor: "#f0647a",
      borderVisible: false,
      wickUpColor: "#22c79a",
      wickDownColor: "#f0647a",
    });
    priceSeries.setData(
      candles
        .filter((row) => row.open !== null && row.high !== null && row.low !== null && row.close !== null)
        .map(
          (row): CandlestickData<Time> => ({
            time: row.time,
            open: row.open!,
            high: row.high!,
            low: row.low!,
            close: row.close!,
          }),
        ),
    );

    if (showVolume) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
      volumeSeries.setData(
        candles
          .filter((row) => row.volume !== null)
          .map(
            (row): HistogramData<Time> => ({
              time: row.time,
              value: row.volume!,
              color: (row.close ?? 0) >= (row.open ?? 0) ? "#22c79a55" : "#f0647a55",
            }),
          ),
      );
    }

    const addAverage = (key: "sma20" | "sma50", color: string) => {
      const series = chart.addSeries(LineSeries, { color, lineWidth: 2, priceLineVisible: false });
      series.setData(
        candles
          .filter((row) => row[key] !== null)
          .map((row): LineData<Time> => ({ time: row.time, value: row[key]! })),
      );
    };
    if (showSma20) addAverage("sma20", "#6aa6ff");
    if (showSma50) addAverage("sma50", "#d69aff");

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [candles, showVolume, showSma20, showSma50]);

  return <div className="chart" ref={containerRef} aria-label="Kursgraf" />;
}
