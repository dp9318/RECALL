import { forwardRef } from 'react';

interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  src?: string;
  alt?: string;
  name?: string;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  shape?: 'circle' | 'square';
}

export const Avatar = forwardRef<HTMLDivElement, AvatarProps>(
  ({ className = '', src, alt, name, size = 'md', shape = 'circle', ...props }, ref) => {
    const sizes = {
      xs: 'w-6 h-6 text-xs',
      sm: 'w-8 h-8 text-sm',
      md: 'w-10 h-10 text-base',
      lg: 'w-12 h-12 text-lg',
      xl: 'w-16 h-16 text-xl',
    };
    
    const shapeClasses = shape === 'circle' ? 'rounded-full' : 'rounded-lg';
    
    const getInitials = (name: string) => {
      return name
        .split(' ')
        .map(n => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2);
    };
    
    const getColorFromName = (name: string) => {
      const colors = [
        'bg-red-500', 'bg-orange-500', 'bg-amber-500', 'bg-green-500',
        'bg-emerald-500', 'bg-teal-500', 'bg-cyan-500', 'bg-sky-500',
        'bg-blue-500', 'bg-indigo-500', 'bg-violet-500', 'bg-purple-500',
        'bg-fuchsia-500', 'bg-pink-500', 'bg-rose-500',
      ];
      let hash = 0;
      for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
      }
      return colors[Math.abs(hash) % colors.length];
    };
    
    if (src) {
      return (
        <div
          ref={ref}
          className={`
            inline-flex items-center justify-center overflow-hidden ${shapeClasses}
            ${sizes[size]} ${className}
          `}
          {...props}
        >
          <img
            src={src}
            alt={alt || name || 'Avatar'}
            className="w-full h-full object-cover"
          />
        </div>
      );
    }
    
    if (name) {
      return (
        <div
          ref={ref}
          className={`
            inline-flex items-center justify-center font-medium text-white ${shapeClasses}
            ${sizes[size]} ${getColorFromName(name)} ${className}
          `}
          {...props}
        >
          {getInitials(name)}
        </div>
      );
    }
    
    return (
      <div
        ref={ref}
        className={`
          inline-flex items-center justify-center ${shapeClasses}
          ${sizes[size]} bg-gray-200 text-gray-500 ${className}
        `}
        {...props}
      >
        <svg className="w-1/2 h-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      </div>
    );
  }
);

Avatar.displayName = 'Avatar';