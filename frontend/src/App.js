import { useState } from "react";
import axios from "axios";
import "./App.css";
import { Authenticator } from "@aws-amplify/ui-react";
import { Amplify } from "aws-amplify";
import { fetchAuthSession } from "aws-amplify/auth";

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolClientId: process.env.REACT_APP_USERPOOL_CLIENTID,
      userPoolId: process.env.REACT_APP_USERPOOL_ID,
      region: process.env.REACT_APP_REGION
    },
  }
});

function App() {
  const [idFile, setidFile] = useState(null);
  const [selfieFile, setSelfieFile] = useState(null);
  const [idFileName, setidFileName] = useState("No file chosen");
  const [selfieFileName, setSelfieFileName] = useState("No file chosen");
  const [count, setCount] = useState(0);
  const [isAttested, setIsAttested] = useState(false);

  const API_URL = `${process.env.REACT_APP_API_URL}id-verify`;

  const convertToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result.split(",")[1]);
      reader.onerror = (error) => reject(error);
    });
  };

  const uploadFiles = async () => {
    if (!idFile || !selfieFile) {
      alert("Please select both an ID and a selfie.");
      return;
    }
  
    try {
      console.log('1. Starting upload process...');
      
      const { tokens } = await fetchAuthSession();
      const token = tokens.idToken.toString();
      
      const idBase64 = await convertToBase64(idFile);
      const selfieBase64 = await convertToBase64(selfieFile);
      
      const headers = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
        "x-api-key": process.env.REACT_APP_API_KEY
      };
  
      console.log('Request details:', {
        url: API_URL,
        headerKeys: Object.keys(headers),
        apiKeyPresent: !!headers['x-api-key']
      });
  
      const response = await axios({
        method: 'post',
        url: API_URL,
        data: {
          identity: idBase64,
          selfie: selfieBase64,
        },
        headers: headers,
        timeout: 30000
      });
  
      console.log('Raw response data:', JSON.stringify(response.data, null, 2));
      console.log('Response received:', {
        status: response.status,
        statusText: response.statusText,
        data: response.data
      });
  
      // Handle the response data
      if (response.status === 200) {
        let resultData;
        
        // Check if response.data is a string that needs parsing
        if (typeof response.data === 'string') {
          resultData = JSON.parse(response.data);
        } else {
          resultData = response.data;
        }
  
        // Check if there's a nested body that needs parsing
        if (resultData.body && typeof resultData.body === 'string') {
          resultData = JSON.parse(resultData.body);
        }
  
        console.log('Processed response data:', resultData);
  
        if (resultData.verificationId) {
          const message = `Verification ID: ${resultData.verificationId}\n` +
                         `Status: ${resultData.status}\n` +
                         `Timestamp: ${resultData.timestamp}`;
          alert(message);
        } else {
          throw new Error('Missing verification ID in response');
        }
      } else {
        throw new Error(`Unexpected status code: ${response.status}`);
      }
  
    } catch (error) {
      console.error('Upload error:', {
        name: error.name,
        message: error.message,
        response: error.response ? {
          status: error.response.status,
          data: error.response.data
        } : 'No response data'
      });
  
      if (error.response) {
        // The request was made and the server responded with a status code
        // that falls out of the range of 2xx
        console.error("Error response details:", {
          data: error.response.data,
          status: error.response.status,
          headers: error.response.headers
        });
        alert(`Server error: ${
          error.response.data.error || 
          (error.response.data.body && JSON.parse(error.response.data.body).error) || 
          "Unknown error"
        }`);
      } else if (error.request) {
        // The request was made but no response was received
        console.error("No response received:", {
          url: API_URL,
          method: "POST"
        });
        alert(
          "The server did not respond. Please try again or contact support if the problem persists."
        );
      } else {
        // Something happened in setting up the request that triggered an Error
        console.error("Request setup error:", error.message);
        alert("Error setting up the request: " + error.message);
      }
    }
  };
  
  const handleIDChange = (e) => {
    const file = e.target.files[0];
    setidFile(file);
    setidFileName(file ? file.name : "No file chosen");
  };

  const handleSelfieChange = (e) => {
    const file = e.target.files[0];
    setSelfieFile(file);
    setSelfieFileName(file ? file.name : "No file chosen");
  };

  const formFields = {
    signUp: {
      email: {
        order: 1,
      },
      username: {
        order: 2,
      },
      password: {
        order: 3,
      },
      confirm_password: {
        order: 4,
      },
    },
  };

  return (
    <Authenticator formFields={formFields}>
      {({ signOut, user }) => (
        <div className="App">
          <header className="App-header">
            <h1>Hello {user?.username}</h1>
            <button onClick={signOut} className="sign-out-btn">
              Sign out
            </button>
          </header>

          <main className="app-main">
            <div className="upload-container">
              <div className="upload-box">
                <h3>Upload Identification (U.S. State Identification, Drivers License or Passport)</h3>
                <input
                  type="file"
                  id="id-file"
                  className="file-input"
                  onChange={handleIDChange}
                  accept="image/*"
                />
                <label htmlFor="id-file" className="file-label">
                  Choose File
                </label>
                <div className="file-name">{idFileName}</div>
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

            <div className="attestation-container">
              <label className="attestation-label">
                <input
                  type="checkbox"
                  checked={isAttested}
                  onChange={(e) => setIsAttested(e.target.checked)}
                  className="attestation-checkbox"
                />
                <span className="attestation-text">
                  I hereby attest, under penalty of perjury, that I am the rightful owner of the 
                  identification document being submitted, and that the selfie photo is a current 
                  and accurate representation of myself. I understand that submitting false 
                  identification or misrepresenting my identity may result in legal consequences.
                </span>
              </label>
            </div>

            <button 
              className={`verify-button ${!isAttested ? 'verify-button-disabled' : ''}`}
              onClick={uploadFiles}
              disabled={!isAttested}
            >
              Verify Identity
            </button>
          </main>
        </div>
      )}
    </Authenticator>
  );
}

export default App;