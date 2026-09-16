import { useEffect } from 'react';
import Navbar from './Navbar';
import AboutSection from './AboutSection';
import './About.css';

function About() {
  useEffect(() => {
    document.body.style.overflow = 'auto';
    return () => { document.body.style.overflow = 'hidden'; };
  }, []);

  return (
    <div className="about">
      <Navbar />
      <AboutSection />
    </div>
  );
}

export default About;
