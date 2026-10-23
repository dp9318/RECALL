import React, { forwardRef } from 'react';
import recallLogoSrc from '../../assets/RECALL-logo-3.svg';

export { recallLogoSrc };

export type RecallLogoSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | number;

export interface RecallLogoProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * Size of the emblem:
   * - 'xs': 20px (inline / avatar badge)
   * - 'sm': 28px (compact header / small inline)
   * - 'md': 34px (sidebar / standard navigation, default)
   * - 'lg': 48px (prominent display / cards)
   * - 'xl': 72px (welcome / empty states / splash)
   * - number: custom pixel dimension (e.g. 40)
   */
  size?: RecallLogoSize;
  /**
   * Custom width override for the emblem in pixels or CSS value
   */
  width?: number | string;
  /**
   * Custom height override for the emblem in pixels or CSS value
   */
  height?: number | string;
  /**
   * Whether to render the RECALL wordmark next to the emblem
   */
  withWordmark?: boolean;
  /**
   * Optional custom CSS class for the wordmark text
   */
  wordmarkClassName?: string;
  /**
   * Optional custom CSS class for the emblem <img> element
   */
  imgClassName?: string;
  /**
   * Optional secondary subtitle / tagline beneath the wordmark
   */
  subtitle?: string;
  /**
   * Accessible alt text for the emblem (defaults to 'RECALL')
   */
  alt?: string;
}

const SIZE_MAP: Record<'xs' | 'sm' | 'md' | 'lg' | 'xl', { px: number; textClass: string; gapClass: string }> = {
  xs: { px: 20, textClass: 'text-xs font-bold tracking-wider', gapClass: 'gap-1.5' },
  sm: { px: 28, textClass: 'text-sm font-bold tracking-tight', gapClass: 'gap-2' },
  md: { px: 34, textClass: 'text-lg font-bold tracking-tight', gapClass: 'gap-2.5' },
  lg: { px: 48, textClass: 'text-2xl font-bold tracking-tight', gapClass: 'gap-3' },
  xl: { px: 72, textClass: 'text-3xl font-extrabold tracking-tight', gapClass: 'gap-4' },
};

export const RecallLogo = forwardRef<HTMLDivElement, RecallLogoProps>(
  (
    {
      size = 'md',
      width,
      height,
      withWordmark = false,
      wordmarkClassName = '',
      imgClassName = '',
      subtitle,
      alt = 'RECALL logo',
      className = '',
      ...rest
    },
    ref
  ) => {
    let emblemDim: number;
    let textClass = 'text-lg font-bold tracking-tight';
    let gapClass = 'gap-2.5';

    if (typeof size === 'number') {
      emblemDim = size;
      if (size <= 22) {
        textClass = 'text-xs font-bold tracking-wider';
        gapClass = 'gap-1.5';
      } else if (size <= 30) {
        textClass = 'text-sm font-bold tracking-tight';
        gapClass = 'gap-2';
      } else if (size <= 40) {
        textClass = 'text-lg font-bold tracking-tight';
        gapClass = 'gap-2.5';
      } else if (size <= 56) {
        textClass = 'text-2xl font-bold tracking-tight';
        gapClass = 'gap-3';
      } else {
        textClass = 'text-3xl font-extrabold tracking-tight';
        gapClass = 'gap-4';
      }
    } else {
      const config = SIZE_MAP[size] || SIZE_MAP.md;
      emblemDim = config.px;
      textClass = config.textClass;
      gapClass = config.gapClass;
    }

    const finalWidth = width !== undefined ? width : emblemDim;
    const finalHeight = height !== undefined ? height : emblemDim;

    return (
      <div
        ref={ref}
        className={`inline-flex items-center ${withWordmark ? gapClass : ''} ${className}`}
        {...rest}
      >
        <img
          src={recallLogoSrc}
          alt={alt}
          width={typeof finalWidth === 'number' ? finalWidth : undefined}
          height={typeof finalHeight === 'number' ? finalHeight : undefined}
          style={{
            width: typeof finalWidth === 'number' ? `${finalWidth}px` : finalWidth,
            height: typeof finalHeight === 'number' ? `${finalHeight}px` : finalHeight,
            aspectRatio: '1 / 1',
          }}
          className={`object-contain flex-shrink-0 select-none ${imgClassName}`}
          loading="eager"
          decoding="async"
        />

        {withWordmark && (
          <div className="flex flex-col min-w-0 leading-none">
            <span
              className={`text-text-primary uppercase ${textClass} ${wordmarkClassName}`}
            >
              RECALL
            </span>
            {subtitle && (
              <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider mt-0.5 truncate">
                {subtitle}
              </span>
            )}
          </div>
        )}
      </div>
    );
  }
);

RecallLogo.displayName = 'RecallLogo';
