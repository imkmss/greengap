import { useNavigate, useLocation } from 'react-router-dom';

function Navbar({ activeSection }) {
  const navigate = useNavigate();
  const location = useLocation();

  const scrollColor = (section) =>
    activeSection === section ? { color: '#ff2626' } : {};

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <button className="brand-title" onClick={() => navigate('/')}>GreengapFinder</button>
        <span className="brand-subtitle">t e s t i n g ... </span>
      </div>
      <div className="navbar-menu">
        <button
          className={`nav-btn ${location.pathname === '/about' ? 'active' : ''}`}
          style={scrollColor('about')}
          onClick={() => navigate('/about')}
        ><b>About</b></button>
        <button
          className={`nav-btn ${location.pathname === '/data' ? 'active' : ''}`}
          style={scrollColor('data')}
          onClick={() => navigate('/data')}
        ><b>Data</b></button>
        <button
          className={`nav-btn ${location.pathname === '/empty' ? 'active' : ''}`}
          style={scrollColor('empty')}
          onClick={() => navigate('/empty')}
        ><b>Empty</b></button>
        <button
          className={`nav-btn ${location.pathname === '/contact' ? 'active' : ''}`}
          style={scrollColor('contact')}
          onClick={() => navigate('/contact')}
        ><b>Contact</b></button>
      </div>
    </nav>
  );
}

export default Navbar;
