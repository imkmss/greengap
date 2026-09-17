import { useEffect } from 'react';
import Navbar from './Navbar';
import './About.css';

function Mypage() {
  useEffect(() => {
    document.body.style.overflow = 'auto';
    return () => { document.body.style.overflow = 'hidden'; };
  }, []);

  return (
    <div className="about">
      <Navbar />
      <div className="about-content">
        <section className="about-hero">
          <h1 className="about-hero-title">My Page</h1>
          <p className="about-hero-sub">준비 중입니다</p>
        </section>
      </div>
    </div>
  );
}

export default Mypage;
