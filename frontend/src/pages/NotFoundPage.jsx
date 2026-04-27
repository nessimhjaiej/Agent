import { useNavigate } from 'react-router-dom';
import AnimatedPage from '../components/AnimatedPage';

export default function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <AnimatedPage className="h-full w-full flex items-center justify-center px-4">
      <div className="w-full max-w-xl text-center">
        <h1 className="text-5xl sm:text-6xl font-bold gradient-text mb-4">404</h1>
        <p className="text-sm" style={{ color: 'var(--text-secondary)', marginBottom: '28px' }}>
          Page not found
        </p>
        <button
          onClick={() => navigate('/')}
          className="rounded-xl text-base font-semibold text-white"
          style={{ background: 'linear-gradient(135deg, #7c3aed, #06b6d4)', padding: '14px 28px', minHeight: '52px', width: 'min(100%, 220px)', marginTop: '4px' }}
        >
          Go to Chat
        </button>
      </div>
    </AnimatedPage>
  );
}
