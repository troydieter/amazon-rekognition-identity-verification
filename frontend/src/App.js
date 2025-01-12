import { useState } from "react";
import axios from "axios";
import "./App.css";
import { Authenticator, useTheme, View, Image, Text, Heading, useAuthenticator, Button } from "@aws-amplify/ui-react";
import { Amplify } from "aws-amplify";

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolClientId: `${process.env.REACT_APP_USERPOOL_CLIENTID}`,
      userPoolId: `${process.env.REACT_APP_USERPOOL_ID}`,
    },
  },
});

function App() {
  const [licenseFile, setLicenseFile] = useState(null);
  const [selfieFile, setSelfieFile] = useState(null);
  const [licenseFileName, setLicenseFileName] = useState("No file chosen");
  const [selfieFileName, setSelfieFileName] = useState("No file chosen");
  const [count, setCount] = useState(0);

  const API_URL = `${process.env.REACT_APP_API_URL}/compare-faces`;

  const convertToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = (error) => reject(error);
    });
  };

  const uploadFiles = async () => {
    if (!licenseFile || !selfieFile) {
      alert("Please select both a driver's license and a selfie.");
      return;
    }
  
    try {
      const licenseBase64 = await convertToBase64(licenseFile);
      const selfieBase64 = await convertToBase64(selfieFile);
  
      const response = await axios.post(`${API_URL}`, 
        {
          dl: licenseBase64,
          selfie: selfieBase64
        },
        {
          headers: {
            'Content-Type': 'application/json',
            'x-api-key': process.env.REACT_APP_API_KEY
          }
        }
      );
    
      console.log('Full response:', response);
  
      if (response.status === 200 && response.data && response.data.body) {
        const bodyData = JSON.parse(response.data.body);
        console.log('Parsed body data:', bodyData);
      
        if (bodyData.verificationId && bodyData.result && typeof bodyData.result.similarity !== 'undefined') {
          const roundedSimilarity = parseFloat(bodyData.result.similarity).toFixed(2);
          const verificationId = bodyData.verificationId;
          let message;
      
          if (roundedSimilarity >= 80) {
            message = `Verification successful.\nVerification ID: ${verificationId}\nSimilarity: ${roundedSimilarity}%`;
          } else if (roundedSimilarity > 0) {
            message = `Verification failed.\nVerification ID: ${verificationId}\nSimilarity: ${roundedSimilarity}%\nThe similarity score is below the required threshold of 80%.`;
          } else {
            message = `Verification failed.\nVerification ID: ${verificationId}\nNo face matches found.`;
          }
      
          alert(message);
        } else {
          throw new Error('Unexpected data format in response body');
        }
      } else {
        console.error('Unexpected response format:', response.data);
        throw new Error('Unexpected response format');
      } 
    } catch (error) {
      console.error('Error:', error);
      alert('An error occurred during the verification process.');
    }
  };
  

  const handleLicenseChange = (e) => {
    const file = e.target.files[0];
    setLicenseFile(file);
    setLicenseFileName(file ? file.name : "No file chosen");
  };

  const handleSelfieChange = (e) => {
    const file = e.target.files[0];
    setSelfieFile(file);
    setSelfieFileName(file ? file.name : "No file chosen");
  };

  const formFields = {
    signUp: {
      email: {
        order: 1
      },
      username: {
        order: 2
      },
      password: {
        order: 3
      },
      confirm_password: {
        order: 4
      }
    }
  };

  return (
    <Authenticator formFields={formFields}>
      {({ signOut, user }) => (
        <div className="App">
          <header className="App-header">
            <h1>Hello {user?.username}</h1>
            <button onClick={signOut} className="sign-out-btn">Sign out</button>
          </header>
          
          <main className="app-main">
            <div className="upload-container">
              <div className="upload-box">
                <h3>Upload Driver's License</h3>
                <input
                  type="file"
                  id="license-file"
                  className="file-input"
                  onChange={handleLicenseChange}
                  accept="image/*"
                />
                <label htmlFor="license-file" className="file-label">
                  Choose File
                </label>
                <div className="file-name">{licenseFileName}</div>
              </div>

              <div className="upload-box">
                <h3>Upload Self-picture (Selfie)</h3>
                <input
                  type="file"
                  id="selfie-file"
                  className="file-input"
                  onChange={handleSelfieChange}
                  accept="image/*"
                />
                <label htmlFor="selfie-file" className="file-label">
                  Choose File
                </label>
                <div className="file-name">{selfieFileName}</div>
              </div>
            </div>

            <button className="verify-button" onClick={uploadFiles}>
              Verify Identity
            </button>
          </main>
        </div>
      )}
    </Authenticator>
  );
}
export default App;